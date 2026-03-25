# ADR-009: Refined Logging & Rotation Strategy

**Date:** 2026-03-25
**Status:** proposed
**Task ID:** TASK-008

## Context
The Kairos engine currently logs at `DEBUG` level to `logs/kairos.log`, rotating only once per day. Outgoing Discord messages are logged with heavy visual formatting, leading to rapid log file growth (potentially several megabytes per day per active session). This creates a risk of disk exhaustion on small VPS instances and makes searching logs difficult.

## Decision
We will implement a more efficient logging strategy focusing on size-based rotation, reduced verbosity for routine events, and level-based filtering.

### 1. Refined Rotation & Retention
- **Size-based triggers**: Add a size limit to rotation (e.g., `20 MB`) alongside the `1 day` limit.
- **Reduced retention**: Decrease `retention` from `7 days` to `3 days` to prioritize recent operational data.
- **Compression**: Retain ZIP compression for rotated logs.

### 2. Log Level Differentiation
- **Default levels**: The file logger will now default to `INFO` instead of `DEBUG`.
- **Dynamic Debug**: Introduce an environment variable `LOG_DEBUG_FILE=true` to allow temporarily enabling verbose debugging without modifying code.

### 3. Log Volume Reduction (Notifier)
- **Compact Format**: Remove the 50-character visual separators (━━━━━━━━━━) from the `Notifier._post` log output.
- **Heartbeat Simplification**: Modify `run_heartbeat` to produce a single-line summary log instead of a multi-line formatted block, while keeping the full block for the actual Discord message.

### 4. Implementation Details
- **`config.py`**: Add `log_rotation_size`, `log_retention_days`, and `log_debug_file` settings.
- **`scheduler.py`**: Update `logger.add` parameters for the file sink.
- **`notifier.py`**: Refactor `_post` to use a more compact log format.

## Rationale
- Size-based rotation protects the VPS from disk overflow in case of a bug or API retry storm.
- `INFO` level for files is sufficient for production monitoring; `DEBUG` is too verbose for long-term storage.
- Removing visual separators reduces the log line count and character count significantly.

## Alternatives Considered
- **Cloud Logging**: Rejected due to additional cost and architectural complexity for a simple VPS setup.
- **Log Splitting**: Considered splitting "Signal Logs" from "System Logs", but rejected to keep troubleshooting simple (one file to trail).

## Definition of Done
- `logs/kairos.log` rotates at the new size/time limits.
- Discord messages appear in logs without large ASCII-art boxes.
- `main()` uses the new configuration from `settings`.
