"""
config.py — All environment variables, constants, and scoring thresholds.
Single source of truth. Every threshold in the system lives here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Dhan API ────────────────────────────────────────────────────────
    dhan_client_id: str
    dhan_access_token: str | None = None
    dhan_client_pin: str | None = None
    dhan_totp_secret: str | None = None
    dhan_base_url: str = "https://api.dhan.co/v2"
    dhan_auth_url: str = "https://auth.dhan.co/app"

    # ── Supabase ─────────────────────────────────────────────────────────
    supabase_url: str
    supabase_key: str

    # ── Discord ──────────────────────────────────────────────────────────
    discord_webhook_url: str          # #environment channel
    discord_health_webhook_url: str   # #system-check channel

    # ── Scheduler ────────────────────────────────────────────────────────
    poll_interval_seconds: int = 60
    heartbeat_interval_seconds: int = 300   # 5 minutes

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Instrument constants ──────────────────────────────────────────────
    nifty_strike_interval: int = 50
    sensex_strike_interval: int = 100   # Phase 2

    # ── Active session windows (IST, 24h) ────────────────────────────────
    session_1_start: tuple[int, int] = (9, 15)
    session_1_end: tuple[int, int] = (11, 0)
    session_2_start: tuple[int, int] = (13, 0)
    session_2_end: tuple[int, int] = (15, 15)

    # ── In-memory buffer sizes ────────────────────────────────────────────
    candle_buffer_size: int = 30   # max candles kept in RAM
    iv_buffer_size: int = 20       # max IV readings kept in RAM

    # ── Retry config ─────────────────────────────────────────────────────
    api_max_retries: int = 3
    api_retry_delay_seconds: float = 5.0
    stale_signal_threshold_minutes: int = 3   # alert if no cycle for this long

    # ── Condition 1: IV Change Rate ───────────────────────────────────────
    # iv_change = ATM_IV_now - ATM_IV_15_minutes_ago
    iv_change_lookback: int = 15          # minutes ago to compare
    iv_change_green: float = 1.5          # above this → 2 pts
    iv_change_yellow: float = 0.0         # above this → 1 pt; below → 0 pts + cap

    # ── Condition 2: Momentum + Directional Consistency ───────────────────
    momentum_candle_window: int = 5              # candles for range + trend check
    momentum_range_green: float = 0.30           # % range for green
    momentum_range_yellow: float = 0.15          # % range for yellow
    momentum_volume_multiplier: float = 1.5      # volume spike threshold
    momentum_volume_lookback: int = 20           # candles for avg volume
    momentum_trend_count_green: int = 4          # out of 5 candles trending
    momentum_trend_count_yellow: int = 3

    # ── Condition 3: OI Flow (no numeric threshold — logic based) ─────────

    # ── Condition 4: Gamma/Theta — DTE-scaled ────────────────────────────
    # DTE >= 3 (lenient — early week, plenty of time)
    gamma_theta_dte_high_green: float = 0.10
    gamma_theta_dte_high_yellow: float = 0.05
    # DTE = 2 (standard)
    gamma_theta_dte_mid_green: float = 0.15
    gamma_theta_dte_mid_yellow: float = 0.08
    # DTE = 1 (strict — expiry day, theta ruthless)
    gamma_theta_dte_low_green: float = 0.25
    gamma_theta_dte_low_yellow: float = 0.15

    # ── Condition 5: PDH/PDL Breakout ─────────────────────────────────────
    pdhl_near_band_pct: float = 0.10   # % within PDH/PDL = "near breakout"

    # ── Condition 6: Move Ratio (30-min realized vs implied) ─────────────
    move_ratio_green: float = 1.0
    move_ratio_yellow: float = 0.7
    move_ratio_lookback_candles: int = 30   # must match candle_buffer_size

    # ── Condition 7: VWAP Distance ───────────────────────────────────────
    vwap_distance_green: float = 0.20    # % from VWAP
    vwap_distance_yellow: float = 0.40

    # ── Scoring thresholds ───────────────────────────────────────────────
    # Total max score = 8 (IV=2, all others=1 each)
    score_go_min: int = 7        # 7–8 → GO
    score_caution_min: int = 4   # 4–6 → CAUTION; 0–3 → AVOID


# Module-level singleton — import this everywhere
settings = Settings()
