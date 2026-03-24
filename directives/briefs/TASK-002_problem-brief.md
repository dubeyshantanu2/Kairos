# Problem Brief — TASK-002
**Date:** 2026-03-24
**Status:** draft

## Problem Statement (Original)
I want to discord alert, but only at start, end and if there are any issues in the process it should send out alert issue

## Problem Statement (Simplified)
Restrict all Discord notifications to three categories: Process Lifecycle Start, Process Lifecycle End, and Functional/Connectivity Issues.

## What We Know
- Heartbeats are already silenced.
- Startup and Session Start/End alerts are active.
- Issue alerts (API warnings, stalls) are active.
- **Environment Alerts** (GO/CAUTION/AVOID) are currently sent on every state change.

## What We Don't Know (Assumptions to Validate)
- **Environment Alerts:** Does "start, end, and issues" exclude the Environment Alerts (GO/CAUTION/AVOID)? If we silence these, the user won't receive trading signals.
- **Definition of "Start":** Does this mean only the `ENGINE STARTING` message, or also every `SESSION ACTIVE` message?
- **Definition of "End":** Does this mean only an `ENGINE STOPPED` message, or also every `SESSION ENDED` message?
- **Warmup Completion:** Is `WARMUP COMPLETE` considered a "start" event or "noise"?

## Edge Cases Identified
- If Environment Alerts are silenced, the system becomes purely a "health monitor" rather than a "signal generator" for Discord.

## Clarifying Questions (max 3)
1. Should we suppress the **Environment Alerts** (GO / CAUTION / AVOID) in the #environment channel? Or should these be kept as they are the primary signals?
2. Does "Start" and "End" refer only to the process running on the VPS, or to each daily trading session?
3. Is "Warmup Complete" considered a "Start" event that you want to see?

## Recommended Next Step
→ Wait for user response to clarifying questions before final design (SAA).
