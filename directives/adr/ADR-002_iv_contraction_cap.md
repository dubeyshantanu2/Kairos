# ADR-002: The IV Contraction Cap

**Date:** 2026-03-22  
**Status:** Active  

## Problem Statement
Long Option premium mathematically necessitates rapid underlying moves to counter the bleeding effect of the Theta metric decay. If the broader market is entering a volatility crush (IV Contracting), option buyers will lose money even if the underlying asset moves favorably in their desired direction.

## Decision Made
We implemented a hard mathematical constraint in `engine.py` called the **IV Contraction Cap**.

Regardless of how many conditions align (Momentum, Delta, PDH break) equating to a standard `🟢 GO` output (7+ Points), if the `score_iv_change()` module detects IV contracting `< 0.0` over the last 15 minutes, the engine forcibly overrides the output.

### Resulting Action
- The Score is capped to a maximum status of `🟡 CAUTION`.
- The `iv_capped` boolean is assigned `True`.
- The orchestrator receives an immediate tag strictly appending: `"⚠️ Strong conditions but IV contracting — wait for IV to stabilize."`

## Alternatives Considered
- **Allowing GO but warning the user:** Relying on human discipline to notice the IV warning mid-trade was deemed unreliable given the high-stress nature of scalping.
- **Setting Score natively to 0:** Distorts the validity of the other 6 performance metrics. The trader *should* know that the environment is otherwise structurally sound (breakouts happening). Setting the score natively to 0 creates heavy false-negatives in the historic reporting DB. 

## Definition of Done
If `score_iv_change()` evaluates to `RED` in a cycle, the final assertion generated must equate to `CAUTION` with `iv_capped = True` in the log structure, effectively short-circuiting green indicators down the chain. Handled automatically via `pytest` fixtures mapping in `test_engine.py`.
