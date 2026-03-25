# ADR-012: Anti-Flap Hysteresis for IV Cap

**Date:** 2026-03-25
**Status:** Active
**Context:** In live production, the IV cap was toggling on and off every minute (flickering). The IV change alternated between tiny negative values and tiny positive values across consecutive cycles, causing the status to flip between `AVOID` and `CAUTION` indefinitely. This created noise in the logs and Discord alerts.

**Decision:**
Implement hysteresis for the IV cap. The cap should turn ON immediately when IV is RED (contractions observed), but it should only turn OFF once IV has recovered meaningfully (expansion >= 0.30).

**Technical Details:**
1.  **Hysteresis Threshold:** Added `iv_cap_release_threshold: float = 0.30` to `config.py`.
2.  **State Tracking:** Added `iv_cap_active: bool` to `SessionState` in `scheduler.py` to track if the cap was triggered in a previous cycle.
3.  **Hysteresis Logic:**
    - If `score.iv_capped` is `True`, set `state.iv_cap_active = True`.
    - If `state.iv_cap_active` is `True` and the current cycle's `iv_change` is `< 0.30`, hold the cap (`score.iv_capped = True`).
    - If `iv_change >= 0.30`, release the cap (`state.iv_cap_active = False`).
4.  **Status Override:** When the cap is held by hysteresis, the system ensures the status is at most `CAUTION`.

**Alternatives Considered:**
- **Time-based cooldown:** Only release the cap after N minutes. Rejected in favor of value-based hysteresis as it directly addresses the signal recovery.
- **Moving Average:** Smooth the IV change value. Rejected as it introduces lag and might miss sudden valid expansions.

**Consequences:**
- Noise reduction: The alternating `AVOID` -> `CAUTION` pattern is eliminated.
- Improved reliability: Signals are only released once market conditions show a sustained positive trend in Implied Volatility.
