# Kairos Engine: Scoring Architecture & Algorithms

**Target Audience:** Engineering Team / System Architects
**Purpose:** Outlines the mathematical logic, lookback parameters, and constraints dictating how the Kairos engine computes its intraday environment scores.

## Overview
The Kairos Intraday Scoring Engine evaluates the market environment over a rolling 60-second cycle. It uses 7 distinct mathematical conditions, yielding a total maximum score of 8 points.
Based on the current score and specifically the state of the Implied Volatility (IV), the engine will output one of three statuses:
* **🟢 GO:** (7–8 Points) Strong directional setup, premium reasonably priced.
* **🟡 CAUTION:** (4–6 Points) Mixed reading, early setup, or capped due to IV contraction.
* **🔴 AVOID:** (0–3 Points) Rangebound, dying premium, theta sink.

---

## 1. Mathematical Condition Breakdown

### Condition 1: Implied Volatility (IV) Change Rate
**Weight:** 2 Points | **Time Parameter:** 15-Minute Lookback
**Logic:** A measure of whether the At-The-Money (ATM) option premium is expanding (inflating) or contracting (deflating) over the last 15 minutes.
* **Data Source:** Rolling 20-candle IV In-Memory Buffer. Compares the current IV (`iv_buffer[-1]`) against the IV from 15 minutes ago (`iv_buffer[-15]`).
* **🟢 Green (2 Pts):** Expansion > +1.5. Premium is inflating.
* **🟡 Yellow (1 Pt):** Expansion between 0.0 and 1.5. Steady premium.
* **🔴 Red (0 Pts):** Contraction < 0.0. Premium is dying. *Triggers the IV Cap (see final section).*
* **Warmup:** Returns CAUTION (1 point) until 15 minutes of uninterrupted data have elapsed.

### Condition 2: Underlying Momentum & Consistency
**Weight:** 1 Point | **Time Parameter:** 5-Minute Lookback + 20-Minute Volume Avg
**Logic:** Ensures the underlying index is actually moving in a uniform direction rather than chopping erratically.
* **Data Source:** Rolling 30-candle OHLCV In-Memory Buffer.
* **Three Checks:**
  1. *Range:* `(Max High - Min Low) / Spot * 100` over the last 5 minutes.
  2. *Volume:* The latest candle volume must be > 1.5x the average volume of the last 20 candles.
  3. *Direction Consistency:* Out of the last 5 candles, are they trending predominately UP or DOWN?
* **🟢 Green (1 Pt):** Range > 0.30% **AND** Volume Spiked **AND** Trend >= 4/5 candles uniform.
* **🔴 Red (0 Pts):** Range < 0.15% **OR** Trend <= 2/5 candles (heavy chop).

### Condition 3: At-The-Money (ATM) Open Interest Flow
**Weight:** 1 Point | **Time Parameter:** Instantaneous (Cycle-by-Cycle Delta)
**Logic:** Uses immediate Option Chain OI Changes to gauge institutional conviction.
* **Data Source:** Live ATM CE & PE Option Rows.
* **🟢 Green (1 Pt):** Strong conviction. e.g. CE writing (adding OI) + PE unwinding (removing OI) = Bearish Conviction.
* **🟡 Yellow (0.5 Pts):** Mild bias. Only one side showing significant change.
* **🔴 Red (0 Pts):** Both adding heavily (straddle writing/rangebound) or both unwinding heavily (uncertainty).

### Condition 4: DTE-Scaled Gamma/Theta Ratio
**Weight:** 1 Point | **Time Parameter:** Days To Expiry (DTE)
**Logic:** Ensures that the potential acceleration in premium (Gamma) is mathematically worth the inherent time decay penalty (Theta). Scales stricter on expiry days.
* **Data Source:** Live ATM CE Gamma and Theta. Ratio = `Gamma / abs(Theta)`.
* **DTE >= 3 (Lenient):** 🟢 Ratio > 0.10 | 🟡 0.05–0.10 | 🔴 < 0.05
* **DTE = 2 (Standard):** 🟢 Ratio > 0.15 | 🟡 0.08–0.15 | 🔴 < 0.08
* **DTE = 1 (Expiry - Strict):** 🟢 Ratio > 0.25 | 🟡 0.15–0.25 | 🔴 < 0.15

### Condition 5: Previous Day High/Low (PDHL) Breakout
**Weight:** 1 Point | **Time Parameter:** Previous Day Daily Candles
**Logic:** Momentum traders seek expansion beyond yesterday's value area to confirm trend participation.
* **Data Source:** PDH/PDL fetched exactly once at 09:15 session start. Band = 0.10% threshold.
* **🟢 Green (1 Pt):** Price cleanly broke above PDH or below PDL.
* **🟡 Yellow (0.5 Pts):** Price is within 0.10% of either level (testing resistance/support).
* **🔴 Red (0 Pts):** Trapped cleanly inside yesterday's range.

### Condition 6: Realized Move vs Implied Straddle Ratio
**Weight:** 1 Point | **Time Parameter:** 30-Minute Lookback
**Logic:** Asks the question: "Is the market actually delivering the volatility that option sellers are pricing in?" If yes, options are under-priced. If no, they are over-priced.
* **Data Source:**
  1. *Implied Move:* Add the absolute premium points of ATM CE and PE `(Straddle Premium / Spot)`.
  2. *Realized Move:* `(Max High - Min Low)` over the last 30 minutes.
* **Ratio:** `Realized Move % / Implied Move %`
* **🟢 Green (1 Pt):** Ratio > 1.0 (Delivering greater volatile range than priced).
* **🟡 Yellow (0.5 Pts):** Ratio 0.7 - 1.0 (Fair pricing).
* **🔴 Red (0 Pts):** Ratio < 0.7 (Premium is entirely overvalued, theta sink).
* **Warmup:** Returns CAUTION until 30 minutes of uninterrupted data have elapsed.

### Condition 7: VWAP Distance Expansion
**Weight:** 1 Point | **Time Parameter:** Current Session (Resets Daily)
**Logic:** Moving too far from the session VWAP (Volume Weighted Average Price) implies technical over-extension and increases the probability of mean-reversion, discouraging fresh continuation entries.
* **Data Source:** Latest incrementally calculated VWAP since 09:15 session start. Distance = `abs(Spot - VWAP) / VWAP * 100`.
* **🟢 Green (1 Pt):** Distance < 0.20%. Trending close to average value area. Room to run.
* **🟡 Yellow (0.5 Pts):** Distance 0.20% - 0.40%. Mildly extended.
* **🔴 Red (0 Pts):** Distance > 0.40%. Too extended. High risk of exhaustion.

---

## 2. Aggregation & The 'IV Cap' Constraint

To compute the final integer score (0–8), the engine sums the individual points from the 7 conditions.

However, the architecture includes a critical override logic designed purely to protect options buyers from "Theta Burn": **The IV Contraction Cap**.

**How the Cap Works:**
If Condition 1 (IV Change Rate) evaluates to **🔴 RED** (IV is actively contracting/shrinking), the system determines that holding long premium is inherently hostile, regardless of how strong the other technical signals are.
* If a cycle computes a total score of `7` or `8` (which normally triggers a 🟢 GO signal)...
* But the IV Condition is 🔴 RED...
* The engine forcibly lowers the final status to **🟡 CAUTION**, attaches an `iv_capped = TRUE` flag, and gracefully informs the orchestrator not to broadcast a GO signal.

This ensures that the trader is never told a setup is "perfect" while underlying premiums are actively being drained by falling volatility.
