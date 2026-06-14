# ADR-021 OI Flow Rolling Consensus Filter
**Date:** 2026-06-14
**Status:** Active

## Context
The Condition 3 (OI Flow) scoring engine runs on a 1-minute cycle. However, this high frequency introduces severe signal instability:
1. **Zero-Cross Price Jitter:** Tiny price fluctuations around zero flip the price change sign, causing the derived phase to cycle between Long Buildup and Short Buildup every minute.
2. **15-Minute Anchor Reset:** The 15-minute anchored window resets the OI baseline to zero at the start of every 15-minute block. This guarantees that for the first few minutes of a block, the OI change cannot exceed the threshold, resetting the phase to `Neutral` (RED).
3. **Transient Dhan Data Noise:** Brief limit order executions cause temporary spikes in OI or Greeks that disappear in the next cycle.

We need to stabilize the signal and improve overall quality without losing the 1-minute resolution of the other indicators.

## Decision
We will implement a **Rolling Consensus Filter** on top of the 1-minute OI Flow evaluation:

1. **Rolling Results Buffer:**
   - Maintain a rolling buffer (`oi_flow_buffer`) of the last 8 `OIFlowResult` objects (T-0 to T-7) inside [SessionState](file:///Users/manmadeanyme/Documents/Work/Kairos/src/kairos/scheduler.py#L32).
   - In each cycle, evaluate the raw 1-minute OI Flow result, append it to the buffer, and then compute a consolidated result from the buffer.

2. **Consolidation Rules:**
   - **Score:** The final score is GREEN (1 pt) if at least 5 out of the last 8 cycles (`oi_consensus_green_threshold` = 5) had a raw GREEN score. Otherwise, RED (0 pts).
   - **Phase:** The reported phase is the most frequent (mode) phase present in the buffer.
   - **Safety Override:** If a critical risk indicator—specifically a **Vega Trap** or a **GEX Pin**—is active in $\ge 3$ cycles (`oi_consensus_trap_threshold` = 3) out of the last 8, the consolidated score is immediately forced to RED (0 pts) to prioritize capital protection.

3. **Configurability:**
   - Add parameters to [Settings](file:///Users/manmadeanyme/Documents/Work/Kairos/src/kairos/config.py#L9):
     - `oi_consensus_window: int = 8`
     - `oi_consensus_green_threshold: int = 5`
     - `oi_consensus_trap_threshold: int = 3`

## Rationale
- **Smoothing Reset Drops:** When the 15-minute block resets, the raw signal momentarily drops to `Neutral`. The consensus filter will maintain the previous buildup phase for a few minutes while the new block builds, smoothing out the hard boundary reset.
- **Filtering Noise:** Transient 1-2 minute fluctuations in price direction or volume will not trigger signal flips.
- **Balanced Latency:** An 8-minute window requires a trend to be sustained for 5 minutes (5 cycles) before outputting GREEN, providing an optimal balance between responsiveness and stability.

## Consequences
- The scheduler and engine must be updated to pass and manage the rolling buffer of results.
- Signal updates to Supabase and Discord will be significantly cleaner, reducing trader distraction.
