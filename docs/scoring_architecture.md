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

### Condition 1: Implied Volatility (IV) Change Rate (DTE-Scaled)
**Weight:** 2 Points | **Time Parameter:** 15-Minute Lookback
**Logic:** Measures whether ATM Implied Volatility (IV) is expanding (inflating) or contracting (deflating). Thresholds are dynamic based on Days To Expiry (DTE) per ADR-011.
* **Data Source:** Rolling 20-candle IV In-Memory Buffer. Compares `iv_buffer[-1]` against `iv_buffer[-15]`.
* **DTE >= 3 (Early Week):** 🟢 > +0.50 | 🟡 > 0.00 | 🔴 Below 0.00
* **DTE = 2 (Mid-Week):** 🟢 > +0.30 | 🟡 > -0.20 | 🔴 Below -0.20
* **DTE <= 1 (Expiry):** 🟢 > +0.20 | 🟡 > -0.50 | 🔴 Below -0.50
* **🔴 Red Status:** Triggers the **IV Cap** override to protect against theta-crush.
* **Warmup:** System fetches data silently 15 minutes prior to Session 2 start, ensuring it outputs fully-scored signals (rather than CAUTION) exactly at the 13:00 IST bell. (Morning session warms up naturally from 09:15–09:30).

### Condition 2: Underlying Momentum & Consistency
**Weight:** 1 Point | **Time Parameter:** 5-Minute Lookback + 15-Minute Volume Avg
**Logic:** Ensures the underlying index is actually moving in a uniform direction rather than chopping erratically.

* **Data Source:** Rolling 15-candle OHLCV In-Memory Buffer.
* **Three Checks:**
  1. *Range:* `(Max High - Min Low) / Spot * 100` over the last 5 minutes.
  2. *Volume:* The latest candle volume must be > 1.5x the average volume of the last 20 candles.
  3. *Direction Consistency:* Out of the last 5 candles, are they trending predominately UP or DOWN?
* **🟢 Green (1 Pt):** Range > 0.30% **AND** Volume Spiked **AND** Trend >= 4/5 candles uniform.
* **🔴 Red (0 Pts):** Range < 0.15% **OR** Trend <= 2/5 candles (heavy chop).

### Condition 3: At-The-Money (ATM) Open Interest Flow
**Weight:** 1 Point | **Time Parameter:** 5-Minute Rolling Window (ADR-010)
**Logic:** Gauges institutional conviction by tracking ATM CE/PE building or unwinding, while classifying the broader market trend phase.
* **Data Source:** Live ATM CE & PE Option Rows. Deltas are calculated over a 5-minute rolling window to filter out single-cycle noise.
* **Conviction Scoring:**
  - **🟢 Green (1 Pt):** Unified conviction. CE Building + PE Unwinding (Bearish) OR PE Building + CE Unwinding (Bullish).
  - **🟡 Yellow (0 Pts):** Mild bias. Only one side showing significant movement.
  - **🔴 Red (0 Pts):** Mixed signals. Both sides building (Straddle writing) or both unwinding (Uncertainty).

#### Market Trend Phases (ADR-014)
The engine correlates Price Δ with total ATM OI Δ (CE+PE) over the lookback period to output one of 5 phases in the alert detail:
| Phase | Logic | Interpretation |
|---|---|---|
| **Long Buildup 🟢** | Price ↑, OI ↑ | Fresh buying; aggressive bullishness. |
| **Short Covering 🔵**| Price ↑, OI ↓ | Sellers exiting; technical rally. |
| **Short Buildup 🔴** | Price ↓, OI ↑ | Fresh selling; aggressive bearishness. |
| **Long Unwinding 🟠**| Price ↓, OI ↓ | Buyers liquidating; profit booking. |
| **Neutral 🟡** | OI Δ < 5000 | Consolidation or low participation phase. |

### Condition 4: Averaged Gamma/Theta Ratio (DTE-Scaled)
**Weight:** 1 Point | **Time Parameter:** Days To Expiry (DTE)
**Logic:** Ensures that the potential acceleration in premium (Gamma) justifies the time decay penalty (Theta). Scaled specifically for Dhan API's per-point-squared index terms.
* **Data Source:** Averages both ATM CE and PE: `gamma = (CE+PE)/2` and `theta = (abs(CE)+abs(PE))/2`.
* **Unit Normalization:** Dhan returns `theta` as an absolute ₹-per-day decay (e.g. `-29.3`), while `gamma` is expressed per point² (e.g. `0.00047`). These are on incompatible scales. Before computing the ratio, `theta` is normalized by the current spot price: `theta_normalized = theta / spot_price`. This converts theta to a per-point basis, matching gamma's scale.
* **Ratio:** `gamma / theta_normalized` (rounded to 6 decimal places).
* **Cold-Start Guard:** If `gamma == 0` (session open artifact), returns **YELLOW** status ("data not yet populated") instead of a false-negative RED.
* **DTE >= 3 (Lenient):** 🟢 Ratio > 0.000080 | 🟡 (0 Pts) > 0.000040 | 🔴 Below
* **DTE = 2 (Standard):** 🟢 Ratio > 0.000120 | 🟡 (0 Pts) > 0.000060 | 🔴 Below
* **DTE = 1 (Expiry - Strict):** 🟢 Ratio > 0.000200 | 🟡 (0 Pts) > 0.000080 | 🔴 Below

### Condition 5: Previous Day High/Low (PDHL) Breakout
**Weight:** 1 Point | **Time Parameter:** Previous Day Daily Candles
**Logic:** Momentum traders seek expansion beyond yesterday's value area to confirm trend participation.
* **Data Source:** PDH/PDL fetched via `/charts/historical`. The engine automatically detects the last fully completed trading day (ignoring today's partial candle if present in the response).
* **🟢 Green (1 Pt):** Price cleanly broke above PDH or below PDL.
* **🟡 Yellow (0 Pts):** Price is within 0.10% of either level (testing resistance/support).
* **🔴 Red (0 Pts):** Trapped cleanly inside yesterday's range.

### Condition 6: Realized Move vs Implied Straddle Ratio
**Weight:** 1 Point | **Time Parameter:** 15-Minute Lookback
**Logic:** Asks the question: "Is the market actually delivering the volatility that option sellers are pricing in?" If yes, options are under-priced. If no, they are over-priced.
* **Data Source:**
  1. *Implied Move:* Add the absolute premium points of ATM CE and PE `(Straddle Premium / Spot)`. To match the realized window, this is scaled down to a 15-minute equivalent using the square-root-of-time rule: `implied_pct * sqrt(15 / total_remaining_mins)`.
  2. *Realized Move:* `(Max High - Min Low)` over the last 15 minutes.
* **Ratio:** `Realized Move % / Scaled Implied Move %`
* **🟢 Green (1 Pt):** Ratio > 1.0 (Delivering greater volatile range than priced).
* **🟡 Yellow (0 Pts):** Ratio 0.7 - 1.0 (Fair pricing).
* **🔴 Red (0 Pts):** Ratio < 0.7 (Premium is entirely overvalued, theta sink).
* **Warmup:** System fetches data silently 15 minutes prior to Session 2 start to fully populate the buffer.

### Condition 7: VWAP Distance Expansion
**Weight:** 1 Point | **Time Parameter:** Current Session (Resets Daily)
**Logic:** Moving too far from the session VWAP (Volume Weighted Average Price) implies technical over-extension and increases the probability of mean-reversion, discouraging fresh continuation entries.
* **Data Source:** Latest incrementally calculated VWAP since 09:15 session start. Distance = `abs(Spot - VWAP) / VWAP * 100`.
* **🟢 Green (1 Pt):** Distance < 0.20%. Trending close to average value area. Room to run.
* **🟡 Yellow (0 Pts):** Distance 0.20% - 0.40%. Mildly extended.
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

**Anti-Flap Hysteresis (ADR-012):**
To prevent the status from flickering between `AVOID` and `CAUTION` due to tiny fluctuations near zero, the system applies hysteresis to the cap:
- **Trigger:** The cap turns ON immediately when IV contraction is detected (RED status).
- **Release:** Once active, the cap is only released if IV recovers meaningfully (expansion >= +0.30).
- **Retention:** If IV change is positive but below +0.30, the `iv_capped` flag remains `True`, and the status is held at `CAUTION`.

