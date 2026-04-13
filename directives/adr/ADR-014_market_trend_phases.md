# ADR-014: Market Trend Phases Classification

## Status
Active (2026-04-13)

## Context
While the "OI Flow" condition (Condition 3) previously provided directional conviction (Bullish/Bearish) based on CE/PE building or unwinding, it lacked a broader classification of underlying market behavior. Professional traders often distinguish between "Fresh Longs" (Long Buildup) and "Short Covering" to understand the quality and sustainability of a price move.

## Decision
Implement a 5-phase classification layer within the `score_oi_flow` processor logic.

1. **Classification logic**: Compare the current cycle's spot price and ATM OI against the values from `oi_lookback_cycles` (default: 5 minutes) ago.
2. **Phase Definitions**:
   - **Long Buildup 🟢**: Price Increase + Total OI Increase (> threshold). Indicates aggressive new buying.
   - **Short Covering 🔵**: Price Increase + Total OI Decrease (< -threshold). Indicates sellers of the strike are exiting their positions.
   - **Short Buildup 🔴**: Price Decrease + Total OI Increase (> threshold). Indicates aggressive new shorting.
   - **Long Unwinding 🟠**: Price Decrease + Total OI Decrease (< -threshold). Indicates buyers are exiting/liquidating.
   - **Neutral 🟡**: Total absolute OI change is less than the `trend_phase_oi_threshold`.
3. **Threshold**: Introduce `trend_phase_oi_threshold` (default: 5000) in `config.py` to filter out noise from low-volume fluctuations.
4. **Integration**: The phase is displayed in the `detail` string of the `ConditionResult` for OI Flow, providing human-readable context in Discord alerts.

## Rationale
- **Contextual Awareness**: Distinguishing between a breakout driven by new buyers (Long Buildup) and one driven by squeezed shorts (Short Covering) is critical for assessing the risk of mean reversion.
- **Noise Filtering**: The threshold ensures that minor OI fluctuations don't trigger a phase change and confuse the trader.
- **Minimal Complexity**: By bundling this logic into the existing `score_oi_flow` function, we avoid creating new top-level conditions while enriching the existing broadcast.

## Consequences
- **Lookback Requirement**: The first 5 minutes of a session (or after a symbol change) will show "Neutral" or "Warming up" until the buffer is populated.
- **Detail String Length**: The `detail` field in Supabase will be longer, but the Discord Orchestrator is designed to handle this via NLP transformation.
