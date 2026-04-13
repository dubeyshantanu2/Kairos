# Research Note — IV Trend Threshold Calibration
**Date:** 2026-04-13
**Researcher:** Research & Creativity Agent + Problem Understanding Agent

## Problem Context
The IV Trend condition (Condition 1) has `iv_change_green = 1.5`, meaning ATM IV must jump
by **+1.5 absolute points in 15 minutes** to score GREEN (2/2). In practice, this essentially
never happens on normal trading days. The user's best-ever reading was **+0.21** (YELLOW, 1/2).

This means:
- IV Trend is almost **permanently RED (0/2)** → permanent IV Cap → system can **never** reach GO status
- The 2 points allocated to IV Trend are wasted — they never contribute to the score
- The IV Cap, designed as a safety valve, is functioning as a permanent blockade

## What We Know About NIFTY ATM IV Behavior (15-min windows)

| Metric | Value |
|--------|-------|
| Typical intraday 15-min IV change | -2.0 to +0.5 |
| Most readings cluster around | -0.5 to +0.3 |
| Best observed reading (user data) | +0.21 |
| Reading needed for current GREEN | > +1.5 |
| Probability of +1.5 on normal day | ~0% |
| Events that cause +1.5 | RBI surprise, war, flash crash |

### DTE Context (Critical)

On **DTE=0** (expiry day — user's primary trading day):
- Theta is at maximum → natural downward pressure on IV
- Even a **flat** IV reading (change ≈ 0) is genuinely positive — IV isn't adding to the decay
- A +0.2 reading is actually **impressive** because it's fighting the natural drift
- Normal expiry-day "contraction" of -0.3 over 15 min is theta-related drift, not an IV crisis

On **DTE=3+** (early week):
- Theta is modest, IV drift is more neutral
- You can afford to be demanding — you WANT genuine expansion for multi-day holds
- +0.5 is a reasonable bar for "this IV is actively helping me"

---

## Option A: Simple Recalibration (Single Threshold)

**Summary:** Lower the thresholds to match observed NIFTY IV dynamics. No code structure changes.

```python
# config.py — just change two numbers
iv_change_green: float = 0.3    # > +0.3 → GREEN 2/2
iv_change_yellow: float = -0.3  # > -0.3 → YELLOW 1/2
                                # < -0.3 → RED 0/2 + IV Cap
```

**Pros:**
- Simplest change — two config values
- The user's +0.21 would still be YELLOW, but a +0.35 day would hit GREEN
- IV Cap only fires on genuine contraction (-0.3+), not on flat readings
- System could actually reach GO status on volatile mornings

**Cons:**
- Doesn't account for DTE behavior — a +0.3 reading means very different things on DTE=0 vs DTE=5
- On DTE=0, mild contraction (-0.1 to -0.3) is NORMAL but would still score YELLOW (which is fine)
- On DTE=3+, +0.3 might be too easy — could let through trades where IV stalls later

---

## Option B: DTE-Scaled IV Thresholds (Recommended)

**Summary:** Scale IV thresholds by DTE, exactly like gamma/theta already does. Strictest early week, most lenient on expiry.

```python
# config.py — new DTE-scaled IV thresholds

# DTE >= 3 (early week — demand real expansion for multi-day holds)
iv_change_dte_high_green: float = 0.5
iv_change_dte_high_yellow: float = 0.0

# DTE = 2 (mid-week — moderate)
iv_change_dte_mid_green: float = 0.3
iv_change_dte_mid_yellow: float = -0.2

# DTE = 0-1 (expiry — accept normal theta-drift, only cap on genuine crush)
iv_change_dte_low_green: float = 0.2
iv_change_dte_low_yellow: float = -0.5
```

**How it would have scored your readings:**

| Reading | DTE=0 (expiry) | DTE=2 | DTE≥3 |
|---------|----------------|-------|-------|
| +0.21 | 🟢 GREEN (2/2) | 🟡 YELLOW (1/2) | 🟡 YELLOW (1/2) |
| +0.35 | 🟢 GREEN (2/2) | 🟢 GREEN (2/2) | 🟡 YELLOW (1/2) |
| +0.55 | 🟢 GREEN (2/2) | 🟢 GREEN (2/2) | 🟢 GREEN (2/2) |
| -0.10 | 🟡 YELLOW (1/2) | 🟡 YELLOW (1/2) | 🔴 RED (0/2 + Cap) |
| -0.40 | 🟡 YELLOW (1/2) | 🔴 RED (0/2 + Cap) | 🔴 RED (0/2 + Cap) |
| -0.60 | 🔴 RED (0/2 + Cap) | 🔴 RED (0/2 + Cap) | 🔴 RED (0/2 + Cap) |
| -1.44 (today) | 🔴 RED (0/2 + Cap) | 🔴 RED (0/2 + Cap) | 🔴 RED (0/2 + Cap) |

**Pros:**
- Architecturally consistent — gamma/theta already uses this exact DTE-scaling pattern
- On DTE=0: the user's +0.21 would have scored GREEN — that's correct intuition for expiry day
- On DTE=0: mild contraction (-0.3) doesn't trigger cap — normal expiry behavior
- On DTE=0: only genuine crush (< -0.5) triggers cap — protects against real danger
- On DTE=3+: demands +0.5 for GREEN — appropriate for multi-day option holds
- Today's -1.44 is still RED under ALL DTE tiers — genuine contraction is still caught

**Cons:**
- 6 new config values instead of 2
- Needs code change in `processor.py::score_iv_change()` to accept `dte` parameter
- Slightly more complex mental model for the trader

---

## Option C: Percentile-Based (Future Enhancement)

**Summary:** Log all IV changes to Supabase, compute rolling percentiles, and use the 75th percentile
as the dynamic GREEN threshold. Self-calibrating.

**Pros:** Adapts to changing market regimes automatically
**Cons:** Needs 2+ weeks of data to bootstrap, adds DB dependency to a pure function
**Verdict:** Good Phase 2 idea, not appropriate right now

---

## Recommendation

**Option B (DTE-Scaled)** is the strongest approach because:

1. The **architecture already has the pattern** (gamma/theta does DTE-scaling with the exact same 3-tier structure)
2. It correctly models **the fundamental truth** that IV behavior differs by DTE
3. Your +0.21 on expiry day **was** a genuine signal — the system should have recognized it
4. Today's -1.44 would still correctly fire RED + IV Cap under all tiers
5. The IV Cap becomes a **real safety net** (fires on genuine crush) instead of a **permanent blockade** (fires on any contraction)

## Impact on the IV Cap Behavior

> [!IMPORTANT]
> The IV Cap logic (`iv_capped = c1_iv.status == "RED"`) doesn't need to change.
> The cap will simply fire less often because RED is now harder to trigger,
> especially on DTE=0 where mild contraction is expected behavior.
> This is the correct behavior — the cap was designed to protect against
> IV crush, not against normal expiry-day theta drift.
