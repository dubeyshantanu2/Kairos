# Problem Brief — TASK-001
**Date:** 2026-03-24
**Status:** clarified

## Problem Statement (Original)
can we make it in sucha a way that it triggers only when there is some issue

## Problem Statement (Simplified)
Eliminate periodic "all systems go" heartbeats to reduce channel noise. The system should only notify Discord when a functional or connectivity issue is detected.

## What We Know
- Heartbeats run every 5 minutes (`heartbeat_interval_seconds = 300`) and post "System alive" even when everything is normal.
- There are already failure-specific notification methods: `post_api_warning`, `post_critical_alert`, `post_stale_signal_warning`.

## What We Don't Know (Assumptions to Validate)
- If we remove periodic heartbeats, should we still have a "System Started" and "Session Started" notification? (User said "only when there is some issue", but these are useful for tracking engine life).
- Should we add a periodic "Still Alive" check that only logs locally but doesn't post to Discord?

## Edge Cases Identified
- **Silent Death:** Without a heartbeat, if the entire process hangs or the internet is cut off at the VPS level, no "Issue" alert can be sent. The user will simply see silence.
- **Warmup:** Warmup status is currently part of the heartbeat. We need to decide if "Warmup Complete" is an "Issue" or "Status Update" (likely status update, should probably be kept or moved).

## Contradictions Found
- None.

## Recommended Next Step
→ Software Architect Agent (SAA) to create ADR-006 to redefine Health Reporting logic.

