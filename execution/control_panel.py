"""
control_panel.py — Kairos CLI Control Panel.

Provides direct terminal-based control over the monitoring sessions, allowing developers
to start and stop monitoring without using the Discord Orchestrator bot. This script
interacts directly with the Supabase `session_config` table.

Usage:
    python execution/control_panel.py start NIFTY 2026-04-16 --type WEEKLY
    python execution/control_panel.py stop
"""

import argparse
import asyncio
import sys
import os
from datetime import date
from loguru import logger

# Ensure 'src' is in path so we can import 'kairos' without PYTHONPATH setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kairos.db import db
from kairos.config import settings

async def main():
    """
    Parses CLI arguments and executes the requested session control command.
    Bypasses the Discord Orchestrator by writing directly to the Supabase bridge.
    """
    parser = argparse.ArgumentParser(description="Kairos CLI Control Panel (Discord Orchestrator Bypass)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Start command
    start_p = subparsers.add_parser("start", help="Start monitoring a symbol")
    start_p.add_argument("symbol", type=str, help="Symbol to monitor (e.g. NIFTY, SENSEX)")
    start_p.add_argument("expiry", type=str, help="Expiry date in YYYY-MM-DD format")
    start_p.add_argument("--type", type=str, default="WEEKLY", choices=["WEEKLY", "MONTHLY"], help="Expiry type (default: WEEKLY)")
    
    # Stop command
    stop_p = subparsers.add_parser("stop", help="Stop the currently active session")

    args = parser.parse_args()

    # Minimal logging for the CLI output
    logger.remove()
    logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>", level="INFO")

    logger.info("Connecting to Supabase (bypassing Discord)...")
    await db.start()
    
    try:
        if args.command == "start":
            try:
                expiry_dt = date.fromisoformat(args.expiry)
            except ValueError:
                logger.error("Invalid date format. Please use YYYY-MM-DD")
                return

            await db.set_active_session(symbol=args.symbol.upper(), expiry=expiry_dt, expiry_type=args.type)
            logger.success(f"✅ Successfully initiated ACTIVE {args.symbol.upper()} session for {args.expiry}")
            logger.info("The scheduler will pick this up automatically within 60 seconds.")
            
        elif args.command == "stop":
            await db.stop_active_session()
            logger.success("✅ Successfully marked active session as STOPPED")
            logger.info("The scheduler will halt monitoring on its next tick.")
            
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    finally:
        await db.stop()

if __name__ == "__main__":
    asyncio.run(main())
