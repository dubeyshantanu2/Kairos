"""
processor.py — Pure functions for all 7 scoring conditions.
No I/O, no side effects. Each function takes data, returns a ConditionResult.
All data comes from in-memory buffers or the current cycle's fetched objects.
"""

from collections import deque
from typing import Optional

from kairos.config import settings
from kairos.models import ATMStrikes, ConditionResult, OHLCVCandle, PreviousDayLevels


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _result(name: str, status: str, points: int, max_points: int, detail: str) -> ConditionResult:
    return ConditionResult(
        name=name,
        status=status,
        points=points,
        max_points=max_points,
        detail=detail,
    )


def _caution(name: str, max_points: int, reason: str = "Warming up") -> ConditionResult:
    """Default CAUTION result used during buffer warmup."""
    return _result(name, "YELLOW", max_points // 2, max_points, reason)


# ─────────────────────────────────────────────────────────────────────────────
# Condition 1 — IV Change Rate (max 2 points)
# ─────────────────────────────────────────────────────────────────────────────

def score_iv_change(iv_buffer: deque) -> ConditionResult:
    """
    Measures whether At-The-Money (ATM) Implied Volatility (IV) is expanding or contracting.
    
    This function compares the current IV against the IV from `iv_change_lookback` (default: 15)
    periods ago to determine if option premiums are inflating or experiencing theta crush.
    
    :param iv_buffer: A rolling in-memory deque containing the recent history of IV floats.
    :type iv_buffer: collections.deque
    :return: A ConditionResult mapping the points (Max: 2) and the status. 
             Returns RED (0 pts) if IV is contracting, which triggers the systemic IV Cap.
    :rtype: ConditionResult
    """
    lookback = settings.iv_change_lookback

    if len(iv_buffer) < lookback:
        remaining = lookback - len(iv_buffer)
        return _caution("iv_trend", 2, f"Warming up — {remaining} readings needed")

    iv_now = iv_buffer[-1]
    iv_then = iv_buffer[-lookback]
    change = round(iv_now - iv_then, 3)

    if change > settings.iv_change_green:
        return _result("iv_trend", "GREEN", 2, 2, f"+{change:.2f} — IV expanding")
    elif change >= settings.iv_change_yellow:
        return _result("iv_trend", "YELLOW", 1, 2, f"+{change:.2f} — mild expansion")
    else:
        return _result("iv_trend", "RED", 0, 2, f"{change:.2f} — IV contracting")


# ─────────────────────────────────────────────────────────────────────────────
# Condition 2 — Underlying Momentum + Directional Consistency (max 1 point)
# ─────────────────────────────────────────────────────────────────────────────

def score_momentum(candle_buffer: deque) -> ConditionResult:
    """
    Evaluates underlying momentum using price range, volume spikes, and directional consistency.
    
    Extracts the last 5 candles to determine if the price is trending cleanly or violently chopping.
    Checks volume against a 20-candle moving average to confirm institutional participation.
    
    :param candle_buffer: A rolling deque of the last 15 1-minute OHLCVCandle objects.
    :type candle_buffer: collections.deque
    :return: A ConditionResult object mapping status (GREEN requires Range > 0.3%, Volume Spike, and >=4/5 trend). Max points: 1.
    :rtype: ConditionResult
    """
    window = settings.momentum_candle_window
    vol_lookback = settings.momentum_volume_lookback

    if len(candle_buffer) < window:
        return _caution("momentum", 1, f"Warming up — need {window} candles")

    recent: list[OHLCVCandle] = list(candle_buffer)[-window:]
    all_candles: list[OHLCVCandle] = list(candle_buffer)

    # Part A — Range and volume
    price_high = max(c.high for c in recent)
    price_low = min(c.low for c in recent)
    current_close = recent[-1].close

    price_range = price_high - price_low
    range_pct = (price_range / current_close) * 100

    # Volume spike: current vs average of last N candles
    if len(all_candles) >= vol_lookback:
        avg_vol = sum(c.volume for c in all_candles[-vol_lookback:]) / vol_lookback
    else:
        avg_vol = sum(c.volume for c in all_candles) / len(all_candles)

    current_vol = recent[-1].volume
    volume_spike = current_vol > (avg_vol * settings.momentum_volume_multiplier)

    # Part B — Directional consistency (how many candles trend in same direction)
    closes = [c.close for c in recent]
    up_count = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1])
    down_count = sum(1 for i in range(1, len(closes)) if closes[i] < closes[i - 1])
    trend_count = max(up_count, down_count)

    direction = "up" if up_count > down_count else "down"

    # Score
    detail = (
        f"{range_pct:.2f}% range, "
        f"{'vol spike' if volume_spike else 'no vol spike'}, "
        f"trend {trend_count}/5 {direction}"
    )

    if (
        range_pct > settings.momentum_range_green
        and volume_spike
        and trend_count >= settings.momentum_trend_count_green
    ):
        return _result("momentum", "GREEN", 1, 1, detail)
    elif (
        range_pct < settings.momentum_range_yellow
        or trend_count <= 2
    ):
        return _result("momentum", "RED", 0, 1, detail)
    else:
        return _result("momentum", "YELLOW", 0, 1, detail)


# ─────────────────────────────────────────────────────────────────────────────
# Condition 3 — OI Flow at ATM (max 1 point)
# ─────────────────────────────────────────────────────────────────────────────

def score_oi_flow(atm: ATMStrikes) -> ConditionResult:
    """
    Checks whether smart money is establishing a directional bias at the ATM strike.
    
    Evaluates instantaneous Open Interest (OI) deltas compared to the previous cycle.
    CE building + PE unwinding = strongly Bearish. PE building + CE unwinding = strongly Bullish.
    
    :param atm: A consolidated ATMStrikes object containing the ATM CE and PE rows.
    :type atm: ATMStrikes
    :return: Extracted conviction result. Returns GREEN for unified direction, RED for straddle writes. (Max: 1)
    :rtype: ConditionResult
    """
    ce_change = atm.ce.oi_change
    pe_change = atm.pe.oi_change

    ce_building = ce_change > 0
    pe_building = pe_change > 0
    ce_unwinding = ce_change < 0
    pe_unwinding = pe_change < 0

    detail = f"CE OI Δ{ce_change:+d} | PE OI Δ{pe_change:+d}"

    if ce_building and pe_unwinding:
        return _result("oi_flow", "GREEN", 1, 1, f"Bullish — {detail}")
    elif pe_building and ce_unwinding:
        return _result("oi_flow", "GREEN", 1, 1, f"Bearish — {detail}")
    elif ce_building and pe_building:
        return _result("oi_flow", "RED", 0, 1, f"Confused — both building | {detail}")
    elif ce_unwinding and pe_unwinding:
        return _result("oi_flow", "RED", 0, 1, f"No conviction — both unwinding | {detail}")
    else:
        # One side flat, one side moving — mild bias
        return _result("oi_flow", "YELLOW", 0, 1, f"Mild bias — {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# Condition 4 — Gamma vs Theta Ratio, DTE-Scaled (max 1 point)
# ─────────────────────────────────────────────────────────────────────────────

def score_gamma_theta(atm: ATMStrikes, dte: int) -> ConditionResult:
    """
    Evaluates whether gamma-driven premium acceleration justifies the theta decay cost.

    Dhan API returns theta as an absolute rupee-per-day decay (e.g. -29.3) and gamma
    as a per-point-squared sensitivity (e.g. 0.00047). These are dimensionally
    incompatible, so theta is normalized by the spot price before computing the ratio:

        theta_normalized = abs(theta) / spot_price
        ratio = gamma / theta_normalized

    This converts theta to the same per-point scale as gamma, yielding a ratio that
    is meaningful and stable across different index levels.

    Thresholds are DTE-scaled: expiry-day conditions require a much higher gamma
    advantage before scoring GREEN.

    :param atm: Consolidated ATMStrikes object containing CE and PE rows and spot price.
    :type atm: ATMStrikes
    :param dte: Days To Expiry for the active contract.
    :type dte: int
    :return: GREEN (1 pt) if gamma advantage is sufficient; YELLOW if borderline; RED if theta dominant.
             Returns YELLOW on cold-start zero-value guards instead of a false RED.
    :rtype: ConditionResult
    """
    # Average CE and PE for robustness against one side having a bad reading
    gamma = (atm.ce.gamma + atm.pe.gamma) / 2
    theta = (abs(atm.ce.theta) + abs(atm.pe.theta)) / 2

    if theta == 0:
        return _result("gamma_theta", "YELLOW", 0, 1, "Theta = 0, data not yet populated")

    # Guard against session-open cold start where Dhan returns gamma=0.0
    if gamma == 0:
        return _result("gamma_theta", "YELLOW", 0, 1, "Gamma = 0, data not yet populated")

    # Normalize theta by spot price before computing the ratio.
    # Dhan returns theta as an absolute ₹-per-day decay (e.g. -29.3), while gamma is
    # expressed per point² (e.g. 0.00047). Dividing by spot_price converts theta to a
    # % basis, making both quantities dimensionally compatible for a meaningful ratio.
    theta_normalized = theta / atm.spot_price
    ratio = round(gamma / theta_normalized, 6)  # 6 decimal places — values are in 0.0000xx range

    # Select thresholds based on DTE
    if dte >= 3:
        green_thresh = settings.gamma_theta_dte_high_green
        yellow_thresh = settings.gamma_theta_dte_high_yellow
        scale_label = "DTE≥3"
    elif dte == 2:
        green_thresh = settings.gamma_theta_dte_mid_green
        yellow_thresh = settings.gamma_theta_dte_mid_yellow
        scale_label = "DTE=2"
    else:
        green_thresh = settings.gamma_theta_dte_low_green
        yellow_thresh = settings.gamma_theta_dte_low_yellow
        scale_label = "DTE=1"

    detail = f"Ratio {ratio:.6f} ({scale_label} scale)"

    if ratio > green_thresh:
        return _result("gamma_theta", "GREEN", 1, 1, f"{detail} — Gamma favored")
    elif ratio > yellow_thresh:
        return _result("gamma_theta", "YELLOW", 0, 1, f"{detail} — borderline")
    else:
        return _result("gamma_theta", "RED", 0, 1, f"{detail} — Theta dominant")


# ─────────────────────────────────────────────────────────────────────────────
# Condition 5 — Previous Day High/Low Breakout (max 1 point)
# ─────────────────────────────────────────────────────────────────────────────

def score_pdhl_breakout(
    spot_price: float,
    prev_levels: PreviousDayLevels,
) -> ConditionResult:
    """
    Calculates if the current spot price has escaped the previous day's value area.
    
    Examines if the asset is trending cleanly above the Previous Day High (PDH) or
    below the Previous Day Low (PDL), representing verified momentum.
    
    :param spot_price: The underlying asset's current live trading value.
    :type spot_price: float
    :param prev_levels: The static PreviousDayLevels loaded identically once at session startup.
    :type prev_levels: PreviousDayLevels
    :return: GREEN if cleanly broken out. YELLOW if trapped in the 0.1% near-band. (Max points: 1)
    :rtype: ConditionResult
    """
    pdh = prev_levels.prev_day_high
    pdl = prev_levels.prev_day_low
    near_band = spot_price * (settings.pdhl_near_band_pct / 100)

    detail = f"Spot {spot_price:.0f} | PDH {pdh:.0f} / PDL {pdl:.0f}"

    if spot_price > pdh:
        return _result("pdhl_breakout", "GREEN", 1, 1, f"Above PDH {pdh:.0f} — bullish breakout")
    elif spot_price < pdl:
        return _result("pdhl_breakout", "GREEN", 1, 1, f"Below PDL {pdl:.0f} — bearish breakout")
    elif spot_price >= (pdh - near_band) or spot_price <= (pdl + near_band):
        return _result("pdhl_breakout", "YELLOW", 0, 1, f"Near breakout level | {detail}")
    else:
        return _result("pdhl_breakout", "RED", 0, 1, f"Inside range | {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# Condition 6 — Move Ratio: Realized vs Implied (max 1 point)
# ─────────────────────────────────────────────────────────────────────────────

def score_move_ratio(
    atm: ATMStrikes,
    candle_buffer: deque,
) -> ConditionResult:
    """
    Compares the asset's realized volatile move against the move priced-in by option sellers.
    
    Utilizes a 15-minute lookback of the `candle_buffer` to capture realized `High - Low` range,
    and maps it proportionally against the percentage cost of the ATM Straddle.
    
    :param atm: Standard ATM options object mapping the absolute LTP premiums.
    :type atm: ATMStrikes
    :param candle_buffer: Full rolling deque of the last 15 minutes of price action.
    :type candle_buffer: collections.deque
    :return: GREEN if Ratio > 1.0 (sellers are underpricing the actual volatility). (Max points: 1)
    :rtype: ConditionResult
    """
    lookback = settings.move_ratio_lookback_candles

    if len(candle_buffer) < lookback:
        remaining = lookback - len(candle_buffer)
        return _caution("move_ratio", 1, f"Warming up — {remaining} candles needed")

    # Implied move from straddle price
    straddle = atm.ce.ltp + atm.pe.ltp
    spot = atm.spot_price
    implied_pct = (straddle / spot) * 100

    # Realized move over 15 candles
    recent: list[OHLCVCandle] = list(candle_buffer)[-lookback:]
    realized_high = max(c.high for c in recent)
    realized_low = min(c.low for c in recent)
    realized_pct = ((realized_high - realized_low) / spot) * 100

    if implied_pct == 0:
        return _caution("move_ratio", 1, "Straddle price = 0, cannot compute ratio")

    ratio = round(realized_pct / implied_pct, 3)
    detail = f"Ratio {ratio:.2f} (realized {realized_pct:.2f}% / implied {implied_pct:.2f}%)"

    if ratio > settings.move_ratio_green:
        return _result("move_ratio", "GREEN", 1, 1, f"{detail} — delivering > priced")
    elif ratio >= settings.move_ratio_yellow:
        return _result("move_ratio", "YELLOW", 0, 1, f"{detail} — roughly fair value")
    else:
        return _result("move_ratio", "RED", 0, 1, f"{detail} — premium overvalued for move")


# ─────────────────────────────────────────────────────────────────────────────
# Condition 7 — VWAP Distance (max 1 point)
# ─────────────────────────────────────────────────────────────────────────────

def score_vwap_distance(
    spot_price: float,
    candle_buffer: deque,
) -> ConditionResult:
    """
    Ensures the underlying index is not statistically over-extended from the session mean.
    
    VWAP is computed incrementally by the DHAN fetcher since 09:15 IST.
    A distance percentage > 0.40% signifies mean-reversion risk, halting continuation entries.
    
    :param spot_price: The live value of the underlying index.
    :type spot_price: float
    :param candle_buffer: Latest candles used purely to lift the most recent incremental VWAP.
    :type candle_buffer: collections.deque
    :return: Evaluated extension risk mapping GREEN/YELLOW/RED. (Max points: 1)
    :rtype: ConditionResult
    """
    if not candle_buffer:
        return _caution("vwap_distance", 1, "No candles yet")

    latest: OHLCVCandle = list(candle_buffer)[-1]
    vwap = latest.vwap

    if vwap == 0:
        return _caution("vwap_distance", 1, "VWAP not yet calculated")

    distance_pct = abs(spot_price - vwap) / vwap * 100
    direction = "above" if spot_price > vwap else "below"
    detail = f"{distance_pct:.2f}% {direction} VWAP {vwap:.0f}"

    if distance_pct < settings.vwap_distance_green:
        return _result("vwap_distance", "GREEN", 1, 1, f"{detail} — room to run")
    elif distance_pct <= settings.vwap_distance_yellow:
        return _result("vwap_distance", "YELLOW", 0, 1, f"{detail} — mildly extended")
    else:
        return _result("vwap_distance", "RED", 0, 1, f"{detail} — extended, exhaustion risk")
