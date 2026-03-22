"""
models.py — All Pydantic data models for Kairos.
These define the shape of every data object flowing through the system.
No business logic here — only structure and validation.
"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


class OptionChainRow(BaseModel):
    """One strike/type row from the Dhan option chain API response."""

    model_config = ConfigDict(frozen=False)

    timestamp: datetime
    symbol: str                  # "NIFTY" or "SENSEX"
    expiry: date
    strike: int
    option_type: str             # "CE" or "PE"
    iv: float                    # implied volatility
    delta: float
    gamma: float
    theta: float
    vega: float
    oi: int                      # open interest
    oi_change: int               # OI change vs previous snapshot
    volume: int
    ltp: float                   # last traded price
    bid: float
    ask: float

    @field_validator("option_type")
    @classmethod
    def validate_option_type(cls, v: str) -> str:
        if v not in ("CE", "PE"):
            raise ValueError(f"option_type must be CE or PE, got {v}")
        return v

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if v not in ("NIFTY", "SENSEX"):
            raise ValueError(f"symbol must be NIFTY or SENSEX, got {v}")
        return v


class OHLCVCandle(BaseModel):
    """One 1-minute OHLCV candle for the underlying index."""

    model_config = ConfigDict(frozen=False)

    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float    # calculated incrementally by fetcher each cycle


class PreviousDayLevels(BaseModel):
    """Previous trading day's high and low — fetched once at session start."""

    model_config = ConfigDict(frozen=False)

    symbol: str
    trade_date: date             # today's date (these levels apply to today)
    prev_day_high: float
    prev_day_low: float
    fetched_at: datetime


class SessionConfig(BaseModel):
    """Active monitoring session as selected by trader via Discord /start-monitor."""

    model_config = ConfigDict(frozen=False)

    symbol: str
    expiry: date
    expiry_type: str             # "WEEKLY" or "MONTHLY"
    status: str                  # "ACTIVE" or "STOPPED"

    @field_validator("expiry_type")
    @classmethod
    def validate_expiry_type(cls, v: str) -> str:
        if v not in ("WEEKLY", "MONTHLY"):
            raise ValueError(f"expiry_type must be WEEKLY or MONTHLY, got {v}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("ACTIVE", "STOPPED"):
            raise ValueError(f"status must be ACTIVE or STOPPED, got {v}")
        return v


class AvailableExpiry(BaseModel):
    """One available expiry date for a symbol — used to build Discord dropdown."""

    model_config = ConfigDict(frozen=False)

    symbol: str
    expiry: date
    expiry_type: str             # "WEEKLY" or "MONTHLY"
    fetched_at: datetime


class ATMStrikes(BaseModel):
    """The ATM CE and PE rows for the current snapshot — computed each cycle."""

    model_config = ConfigDict(frozen=False)

    atm_strike: int
    ce: OptionChainRow
    pe: OptionChainRow
    spot_price: float


class ConditionResult(BaseModel):
    """
    Result of one scored condition.
    Every condition returns this same shape — scoring engine loops over them.
    """

    model_config = ConfigDict(frozen=False)

    name: str          # e.g. "iv_trend", "momentum", "oi_flow"
    status: str        # "GREEN", "YELLOW", "RED"
    points: int        # actual points scored this cycle
    max_points: int    # maximum possible for this condition
    detail: str        # human-readable value, e.g. "+2.1 IV expanding"

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("GREEN", "YELLOW", "RED"):
            raise ValueError(f"status must be GREEN, YELLOW, or RED, got {v}")
        return v


class EnvironmentScore(BaseModel):
    """
    Full scored output of one evaluation cycle.
    This is the central object — written to Supabase and posted to Discord.
    """

    model_config = ConfigDict(frozen=False)

    timestamp: datetime
    symbol: str
    expiry: date
    dte: int                              # days to expiry
    score: int                            # total points scored (0–8)
    max_score: int = 8
    status: str                           # "GO", "CAUTION", "AVOID"
    iv_capped: bool = False               # True if IV contraction cap was applied
    conditions: list[ConditionResult]     # all 7 condition results
    summary_raw: str                      # Python-generated template string
    summary: str = ""                     # Gemini-polished (filled by OpenClaw)
    previous_status: Optional[str] = None # previous cycle's status for change detection

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("GO", "CAUTION", "AVOID"):
            raise ValueError(f"status must be GO, CAUTION, or AVOID, got {v}")
        return v

    @property
    def state_changed(self) -> bool:
        """True if environment status changed from previous cycle."""
        return self.previous_status != self.status

    @property
    def status_emoji(self) -> str:
        """Emoji for the current status."""
        return {"GO": "🟢", "CAUTION": "🟡", "AVOID": "🔴"}.get(self.status, "⚪")

    def get_condition(self, name: str) -> Optional[ConditionResult]:
        """Retrieve a specific condition result by name."""
        return next((c for c in self.conditions if c.name == name), None)


class HealthStatus(BaseModel):
    """System health snapshot posted to #system-check every heartbeat."""

    model_config = ConfigDict(frozen=False)

    timestamp: datetime
    is_fetching: bool             # True if last fetch succeeded
    last_fetch_time: Optional[datetime]
    dhan_api_ok: bool
    supabase_ok: bool
    cycle_count: int              # cycles completed this session
    symbol: str
    expiry: Optional[date]
    warmup_complete: bool         # True once all buffers have enough data
    warmup_cycles_remaining: int  # 0 when fully warmed up
