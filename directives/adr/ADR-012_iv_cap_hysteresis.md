# ADR-012: Anti-Flap Hysteresis for IV Cap

**Date:** 2026-03-25
**Updated:** 2026-04-13
**Status:** Active (revised by ADR-011)
**Context:** In live production, the IV cap was toggling on and off every minute (flickering). The IV change alternated between tiny negative values and tiny positive values across consecutive cycles, causing the status to flip between `AVOID` and `CAUTION` indefinitely. This created noise in the logs and Discord alerts.

**Decision:**
Implement hysteresis for the IV cap. The cap should turn ON immediately when IV is RED, but it should only turn OFF when IV Trend scores GREEN (genuine expansion confirmed).

**Revision (ADR-011):** The original fixed threshold (`iv_cap_release_threshold = 0.30`) was replaced with status-based release. This avoids the contradiction where IV Trend could score GREEN (e.g., +0.25 on DTE=0 where GREEN threshold is > +0.2) but the cap stayed active because +0.25 < 0.30.

**Technical Details:**
1.  **State Tracking:** `iv_cap_active: bool` on `SessionState` in `scheduler.py` tracks if the cap was triggered in a previous cycle.
2.  **Hysteresis Logic (current):**
    - **Cap ON**: `score.iv_capped` is `True` (IV Trend scored RED) → set `state.iv_cap_active = True`
    - **Cap HOLD**: `state.iv_cap_active` is `True` and IV Trend status is not GREEN → keep cap active
    - **Cap OFF**: IV Trend scores GREEN → release cap (`state.iv_cap_active = False`)
3.  **Status Override:** When the cap is held by hysteresis, the system ensures the status is at most `CAUTION`.
4.  **DTE-scaling:** GREEN thresholds are DTE-scaled (ADR-011), so the cap release is automatically stricter early-week (> +0.5) and more lenient on expiry (> +0.2).

**Alternatives Considered:**
- **Time-based cooldown:** Only release the cap after N minutes. Rejected in favor of value-based hysteresis as it directly addresses the signal recovery.
- **Moving Average:** Smooth the IV change value. Rejected as it introduces lag and might miss sudden valid expansions.
- **Fixed threshold (original):** Used `iv_cap_release_threshold = 0.30`. Replaced because it conflicted with DTE-scaled GREEN thresholds.

**Consequences:**
- Noise reduction: The alternating `AVOID` -> `CAUTION` pattern is eliminated.
- Consistency: Cap release and IV Trend GREEN are now the same gate — no contradictions.
- DTE-awareness: Cap release is automatically calibrated to the expiry context.
