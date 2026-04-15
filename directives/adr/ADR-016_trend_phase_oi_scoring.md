# ADR-016: Trend Phase-Driven OI Flow Scoring
**Date:** 2026-04-15
**Status:** Approved

## Problem Statement
The previous `oi_flow` scoring logic was too restrictive, requiring one side (CE or PE) to be actively unwinding to score points. In reality, OI often increases on both sides during market hours, leading to frequent "Confused" (RED) scores even when a clear trend (e.g., Short Buildup) was identified. Additionally, the user wants to avoid trading "pullback" phases like Short Covering and Long Unwinding.

## Decision
1.  **Phase-Based Scoring:** The `score_oi_flow` condition will now derive its status and points directly from the calculated Trend Phase.
2.  **Explicit Point Mapping:**
    - **Long Buildup 🟢**: Scored as **GREEN (1 pt)**. Indicates strong bullish trend continuation.
    - **Short Buildup 🔴**: Scored as **GREEN (1 pt)**. Indicates strong bearish trend continuation.
    - **Short Covering 🔵**: Scored as **RED (0 pts)**. Labeled as a "Pullback" to be avoided.
    - **Long Unwinding 🟠**: Scored as **RED (0 pts)**. Labeled as a "Pullback" to be avoided.
    - **Neutral 🟡**: Scored as **RED (0 pts)**. No directional conviction.
3.  **Straddle Writing Detection:** In "Neutral" phases where both CE and PE OI deltas are positive and significant, the system will explicitly label the situation as "Straddle Writing" to provide better context to the trader.
4.  **Abolish Strict Unwinding Requirement:** We will no longer require one side to be negative to score GREEN, provided the overall Trend Phase is a "Buildup".

## Rationale
- **User Intent:** Aligns strictly with the user's preference to only trade stable "buildup" trends and ignore "pullback" trades.
- **Signal Accuracy:** Reduces false "Confused" alerts when the market is clearly trending despite some hedging activity on the opposing side.
- **Clarity:** Provides more descriptive feedback (e.g., "Bullish — Long Buildup") instead of generic conviction messages.

## Component Changes
- `src/kairos/processor.py`: Refactor `score_oi_flow` logic.
- `tests/test_processor.py`: Update tests to match new phase-to-points mapping.

## Definition of Done
- [ ] `score_oi_flow` returns GREEN (1 pt) for Long/Short Buildup.
- [ ] `score_oi_flow` returns RED (0 pts) for Short Covering and Long Unwinding.
- [ ] `score_oi_flow` returns RED (0 pts) for Neutral phases.
- [ ] Detail strings correctly identify the phase and deltas.
- [ ] All updated tests in `tests/test_processor.py` are passing.
