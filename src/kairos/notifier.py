"""
notifier.py — All Discord communication.
Posts environment alerts to #environment and health messages to #system-check.
Uses Discord webhooks directly — no bot token needed.
"""

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from kairos.config import settings
from kairos.models import ConditionResult, EnvironmentScore, HealthStatus

IST = ZoneInfo("Asia/Kolkata")

# Emoji maps
STATUS_EMOJI = {"GO": "🟢", "CAUTION": "🟡", "AVOID": "🔴"}
CONDITION_EMOJI = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
CONDITION_LABELS = {
    "iv_trend": "IV Trend",
    "momentum": "Momentum",
    "oi_flow": "OI Flow",
    "gamma_theta": "Gamma/θ",
    "pdhl_breakout": "PDH/PDL",
    "move_ratio": "Move",
    "vwap_distance": "VWAP",
}


class Notifier:
    """
    Discord webhook poster.
    Uses a shared httpx.AsyncClient for all requests.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        logger.info("Notifier: HTTP client initialised")

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
        logger.info("Notifier: HTTP client closed")

    async def _post(self, webhook_url: str, payload: dict) -> None:
        """Fire-and-forget webhook POST. Logs on failure, never raises."""
        # Always print payload to terminal for local debugging
        content = payload.get("content", "")
        logger.info(
            "\n"
            + "━" * 50 + "\n"
            + "📢 DISCORD MESSAGE\n"
            + "━" * 50 + "\n"
            + content + "\n"
            + "━" * 50
        )
        if not self._client:
            logger.error("Notifier not started")
            return
        try:
            response = await self._client.post(webhook_url, json=payload)
            if response.status_code not in (200, 204):
                logger.error(
                    f"Discord webhook returned {response.status_code}: "
                    f"{response.text[:200]}"
                )
        except Exception as e:
            logger.error(f"Failed to post to Discord: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # Environment alerts → #environment channel
    # ─────────────────────────────────────────────────────────────────────

    async def post_environment_alert(self, score: EnvironmentScore) -> None:
        """
        Post GO / CAUTION / AVOID alert to #environment channel.
        Only called when state changes.
        """
        status_emoji = STATUS_EMOJI.get(score.status, "⚪")
        cap_note = "  ⚠️ IV Cap Active" if score.iv_capped else ""

        # Build condition lines
        condition_lines = []
        for c in score.conditions:
            emoji = CONDITION_EMOJI.get(c.status, "⚪")
            label = CONDITION_LABELS.get(c.name, c.name)
            pts = f"[{c.points}/{c.max_points}]" if c.max_points > 1 else ""
            condition_lines.append(f"{emoji} {label:<9}: {c.detail} {pts}".rstrip())

        session_label = _get_session_label()
        time_str = datetime.now(IST).strftime("%H:%M IST")

        # Use summary if Gemini has polished it, otherwise fall back to summary_raw
        summary_text = score.summary if score.summary else _generate_fallback_summary(score)

        lines = [
            f"{status_emoji} **ENVIRONMENT: {score.status}**{cap_note}",
            "─" * 34,
            f"Index    : {score.symbol}  |  DTE: {score.dte}",
            f"Session  : {session_label}",
            f"Expiry   : {score.expiry.strftime('%d %b %Y')} ({_expiry_type_label(score)})",
            "─" * 34,
        ] + condition_lines + [
            "─" * 34,
            f"Score    : {score.score}/{score.max_score}",
        ]

        if score.iv_capped:
            lines.append(f"⚠️ Capped at CAUTION — IV contracting")

        lines.append(summary_text)
        lines.append(f"🕐 {time_str}")

        content = "\n".join(lines)
        await self._post(settings.discord_webhook_url, {"content": content})
        logger.info(f"Posted {score.status} alert to #environment — score {score.score}/8")

    # ─────────────────────────────────────────────────────────────────────
    # Health messages → #system-check channel
    # ─────────────────────────────────────────────────────────────────────

    async def post_startup(
        self,
        dhan_ok: bool,
        supabase_ok: bool,
        pdh: float,
        pdl: float,
        symbol: str,
        expiry_str: str,
    ) -> None:
        """Post startup sequence result to #system-check."""
        dhan_status = "✅ Connected" if dhan_ok else "❌ FAILED"
        supa_status = "✅ Connected" if supabase_ok else "❌ FAILED"
        time_str = datetime.now(IST).strftime("%H:%M:%S IST")

        content = "\n".join([
            "ℹ️ **ENGINE STARTING**",
            f"Kairos v{_get_version()} starting on VPS",
            f"Time: {time_str}",
            "",
            f"Dhan API  : {dhan_status}",
            f"Supabase  : {supa_status}",
            f"PDH/PDL   : H={pdh:.0f} / L={pdl:.0f}",
            "",
            "⏳ **WARMUP IN PROGRESS**",
            "Buffers empty — scoring in CAUTION mode",
            "Full scoring available in ~30 minutes (cycle 30)",
            f"Monitoring : {symbol} | {expiry_str}",
        ])
        await self._post(settings.discord_health_webhook_url, {"content": content})

    async def post_warmup_complete(self, symbol: str) -> None:
        """Post warmup complete notice to #system-check."""
        time_str = datetime.now(IST).strftime("%H:%M IST")
        content = (
            f"✅ **WARMUP COMPLETE**\n"
            f"All 7 conditions now scoring normally.\n"
            f"{symbol} | {time_str}"
        )
        await self._post(settings.discord_health_webhook_url, {"content": content})

    async def post_heartbeat(
        self,
        last_fetch_time: Optional[datetime],
        cycle_count: int,
        symbol: str,
        expiry_str: str,
        warmup_complete: bool,
    ) -> None:
        """Post 5-minute heartbeat to #system-check."""
        fetch_str = (
            last_fetch_time.strftime("%H:%M:%S IST")
            if last_fetch_time
            else "Never"
        )
        time_str = datetime.now(IST).strftime("%H:%M IST")
        warmup_note = "" if warmup_complete else "\n⏳ Still warming up..."

        content = "\n".join([
            "💓 **HEARTBEAT** — System alive",
            "─" * 30,
            f"Status    : ✅ Fetching normally",
            f"Last fetch: {fetch_str}",
            f"API       : ✅ Dhan responding",
            f"Cycle     : {cycle_count} of session",
            "─" * 30,
            f"{symbol} | {expiry_str}",
            f"🕐 {time_str}{warmup_note}",
        ])
        await self._post(settings.discord_health_webhook_url, {"content": content})

    async def post_api_warning(self, attempt: int, error_str: str) -> None:
        """Post API failure warning — only called on 'Start' of warning."""
        time_str = datetime.now(IST).strftime("%H:%M:%S IST")
        content = (
            f"⚠️ **DHAN API WARNING (START)**\n"
            f"Failed to fetch data (attempt {attempt})\n"
            f"Error: {error_str}\n"
            f"Monitoring for recovery... | {time_str}"
        )
        await self._post(settings.discord_health_webhook_url, {"content": content})

    async def post_api_recovered(self) -> None:
        """Post API recovery — only called on 'End' of warning."""
        time_str = datetime.now(IST).strftime("%H:%M:%S IST")
        content = (
            f"✅ **DHAN API RECOVERED (END)**\n"
            f"Connectivity restored. Normal operations resumed.\n"
            f"🕐 {time_str}"
        )
        await self._post(settings.discord_health_webhook_url, {"content": content})

    async def post_critical_alert(
        self,
        error_type: str,
        error_detail: str,
        last_signal_time: Optional[datetime],
        action_hint: str,
    ) -> None:
        """
        Post critical system failure to #system-check.
        Tells trader not to trade based on last signal.
        """
        time_str = datetime.now(IST).strftime("%H:%M:%S IST")
        last_signal_str = (
            last_signal_time.strftime("%H:%M IST")
            if last_signal_time
            else "unknown"
        )

        content = "\n".join([
            "🚨 **SYSTEM ALERT — ACTION REQUIRED**",
            "─" * 34,
            f"Error  : {error_type}",
            f"Detail : {error_detail}",
            f"Time   : {time_str}",
            f"Impact : ⚠️ Last signal posted at {last_signal_str} may be STALE",
            "",
            f"Action : {action_hint}",
            "─" * 34,
            "**DO NOT trade based on last GO signal.**",
        ])
        await self._post(settings.discord_health_webhook_url, {"content": content})

    async def post_stale_signal_warning(
        self,
        last_cycle_time: datetime,
        symbol: str,
    ) -> None:
        """
        Post stale signal warning to BOTH channels when engine is unresponsive.
        """
        time_str = datetime.now(IST).strftime("%H:%M IST")
        last_str = last_cycle_time.strftime("%H:%M IST")

        content = (
            f"⚠️ **SIGNAL MAY BE STALE**\n"
            f"Last successful cycle: {last_str}\n"
            f"Current time: {time_str}\n"
            f"Engine appears unresponsive.\n"
            f"**Disregard last environment status until system recovers.**"
        )
        # Post to both channels
        await self._post(settings.discord_webhook_url, {"content": content})
        await self._post(settings.discord_health_webhook_url, {"content": content})

    async def post_stopped(self, symbol: str) -> None:
        """Post engine stopped confirmation to #system-check."""
        time_str = datetime.now(IST).strftime("%H:%M IST")
        content = (
            f"ℹ️ **ENGINE STOPPED**\n"
            f"{symbol} monitoring paused via /stop-monitor\n"
            f"🕐 {time_str}"
        )
        await self._post(settings.discord_health_webhook_url, {"content": content})

    async def post_session_boundary(self, entering: bool, session_name: str) -> None:
        """Post session start/end to #system-check."""
        time_str = datetime.now(IST).strftime("%H:%M IST")
        if entering:
            content = f"✅ **SESSION ACTIVE** — {session_name}\nMonitoring begins | {time_str}"
        else:
            content = f"ℹ️ **SESSION ENDED** — {session_name}\nEngine idle until next session | {time_str}"
        await self._post(settings.discord_health_webhook_url, {"content": content})


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_session_label() -> str:
    now = datetime.now(IST)
    h, m = now.hour, now.minute
    if (9, 15) <= (h, m) <= (11, 0):
        return "Open (09:15–11:00)"
    elif (13, 0) <= (h, m) <= (15, 15):
        return "Post-Lunch (13:00–15:15)"
    return "Outside session"


def _expiry_type_label(score: EnvironmentScore) -> str:
    """Returns 'Weekly' or 'Monthly' — reads from environment_log not directly available here."""
    return "Weekly"   # OpenClaw enriches this from session_config


def _generate_fallback_summary(score: EnvironmentScore) -> str:
    """Minimal fallback summary if Gemini hasn't polished yet."""
    if score.status == "GO":
        return "Conditions favorable for options buying."
    elif score.status == "CAUTION":
        if score.iv_capped:
            return "Strong conditions but IV contracting — wait for IV to stabilize."
        return "Mixed conditions — wait for a cleaner setup."
    else:
        return "⚠️ Premium will decay faster than market moves."


def _get_version() -> str:
    try:
        from kairos import __version__
        return __version__
    except Exception:
        return "0.1.0"


# Module-level singleton
notifier = Notifier()
