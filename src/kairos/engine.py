"""
engine.py — Orchestrates all 7 conditions into a final EnvironmentScore.
Applies IV weighting (2pts), IV contraction cap, and generates summary_raw.
"""

from collections import deque
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from kairos.config import settings
from kairos.models import (
    ATMStrikes,
    ConditionResult,
    EnvironmentScore,
    OHLCVCandle,
    OptionChainRow,
    PreviousDayLevels,
    SessionConfig,
    StrikeCluster,
)
from kairos.processor import (
    score_gamma_theta,
    score_iv_change,
    score_momentum,
    score_move_ratio,
    score_oi_flow,
    score_pdhl_breakout,
    score_vwap_distance,
)

IST = ZoneInfo("Asia/Kolkata")


def find_atm(
    option_chain: list[OptionChainRow],
    spot_price: float,
    strike_interval: int,
) -> ATMStrikes:
    """
    Determine the ATM strike and find the corresponding CE and PE rows.
    ATM = round(spot / interval) * interval
    """
    atm_strike = round(spot_price / strike_interval) * strike_interval

    ce_row = next(
        (r for r in option_chain if r.strike == atm_strike and r.option_type == "CE"),
        None,
    )
    pe_row = next(
        (r for r in option_chain if r.strike == atm_strike and r.option_type == "PE"),
        None,
    )

    if ce_row is None or pe_row is None:
        # Fallback: find closest available strike
        available_strikes = sorted({r.strike for r in option_chain})
        closest = min(available_strikes, key=lambda s: abs(s - spot_price))
        ce_row = next(
            (r for r in option_chain if r.strike == closest and r.option_type == "CE"),
            None,
        )
        pe_row = next(
            (r for r in option_chain if r.strike == closest and r.option_type == "PE"),
            None,
        )

    if ce_row is None or pe_row is None:
        raise ValueError(f"Cannot find ATM CE/PE for spot {spot_price} in option chain")

    return ATMStrikes(
        atm_strike=atm_strike,
        ce=ce_row,
        pe=pe_row,
        spot_price=spot_price,
    )


def build_strike_cluster(
    option_chain: list[OptionChainRow],
    atm_strike: int,
    count: int,
    spot_price: float,
) -> StrikeCluster:
    """
    Extracts high-conviction cluster (ATM ± count strikes).
    Dhan returns a full chain; we find the ATM index and slice.
    """
    # 1. Get unique sorted strikes
    strikes = sorted(list(set(r.strike for r in option_chain)))
    
    try:
        atm_idx = strikes.index(atm_strike)
    except ValueError:
        # Fallback if exact ATM strike missing
        atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm_strike))
    
    start_idx = max(0, atm_idx - count)
    end_idx = min(len(strikes), atm_idx + count + 1)
    
    target_strikes = strikes[start_idx:end_idx]
    
    ce_cluster = [r for r in option_chain if r.strike in target_strikes and r.option_type == "CE"]
    pe_cluster = [r for r in option_chain if r.strike in target_strikes and r.option_type == "PE"]
    
    # Calculate Distance-Weighted Mean for the cluster (ADR-012 refinement)
    # Weights decay linearly from 1.0 (ATM) downwards to ~0.125 at ±7 strikes
    def get_weighted_sum(rows: list[OptionChainRow]) -> tuple[float, float]:
        total_weighted_oi = 0.0
        total_weight = 0.0
        for r in rows:
            # Distance in strikes from ATM: ATM strike is weight 1.0
            # Offset = abs(offset_in_strikes)
            # Weight = 1.0 - (offset / (count + 1))
            try:
                offset = abs(target_strikes.index(r.strike) - target_strikes.index(atm_strike))
            except (ValueError, IndexError):
                offset = 0 # should not happen given target_strikes build logic
            
            weight = max(0.01, 1.0 - (offset / (count + 1)))
            total_weighted_oi += r.oi_change * weight
            total_weight += weight
            
        return total_weighted_oi, total_weight

    ce_w_sum, ce_w_total = get_weighted_sum(ce_cluster)
    pe_w_sum, pe_w_total = get_weighted_sum(pe_cluster)
    
    # Final Mean = Weighted Sum / Total Weight
    ce_mean = ce_w_sum / ce_w_total if ce_w_total > 0 else 0
    pe_mean = pe_w_sum / pe_w_total if pe_w_total > 0 else 0
    
    return StrikeCluster(
        atm_strike=atm_strike,
        spot_price=spot_price,
        ce_cluster=ce_cluster,
        pe_cluster=pe_cluster,
        total_ce_oi_change=int(round(ce_mean)),
        total_pe_oi_change=int(round(pe_mean)),
    )



def _determine_status(score: int, iv_capped: bool) -> str:
    """
    Map numeric score to GO / CAUTION / AVOID.
    If IV cap is active, maximum status is CAUTION.
    """
    if score >= settings.score_go_min:
        raw_status = "GO"
    elif score >= settings.score_caution_min:
        raw_status = "CAUTION"
    else:
        raw_status = "AVOID"

    # IV contraction cap — downgrade GO to CAUTION
    if iv_capped and raw_status == "GO":
        return "CAUTION"

    return raw_status


def _build_summary_raw(
    conditions: list[ConditionResult],
    score: int,
    max_score: int,
    iv_capped: bool,
    dte: int,
) -> str:
    """
    Build a compact machine-readable summary string.
    This gets stored in environment_log.summary_raw.
    Gemini/Discord Orchestrator polishes this into the final Discord message.
    """
    parts = []
    for c in conditions:
        emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(c.status, "⚪")
        parts.append(f"{emoji} {c.name}: {c.detail} [{c.points}/{c.max_points}]")

    cap_note = " | ⚠️ IV cap active" if iv_capped else ""
    summary = (
        f"DTE={dte} | Score={score}/{max_score}{cap_note}\n"
        + "\n".join(parts)
    )
    return summary


def evaluate(
    option_chain: list[OptionChainRow],
    candle_buffer: deque,
    iv_buffer: deque,
    prev_levels: PreviousDayLevels,
    spot_price: float,
    dte: int,
    session_config: SessionConfig,
    previous_status: Optional[str] = None,
) -> EnvironmentScore:
    """
    Orchestrates the 7 technical scoring conditions into a unified EnvironmentScore.
    
    This function acts as the core mathematical engine for the Kairos system. It extracts the
    ATM options, delegates processing to the individual scoring modules, sums the points (Max: 8),
    and strictly applies the `iv_capped` logic before yielding a final status.
    
    All inputs are injected from purely in-memory buffers or single-cycle API fetches. 
    Zero disk I/O or network calls occur within this function.
    
    :param option_chain: Full list of current OptionChainRow objects fetched from the broker.
    :type option_chain: list[OptionChainRow]
    :param candle_buffer: Rolling 15-minute buffer of OHLCVCandle data.
    :type candle_buffer: collections.deque
    :param iv_buffer: Rolling 15-minute buffer of Implied Volatility floats.
    :type iv_buffer: collections.deque
    :param prev_levels: PreviousDayLevels loaded cleanly at session startup.
    :type prev_levels: PreviousDayLevels
    :param spot_price: The live value of the underlying index.
    :type spot_price: float
    :param dte: Days To Expiry of the active configuration.
    :type dte: int
    :param session_config: The system configuration dictating target symbols and active flags.
    :type session_config: SessionConfig
    :param previous_status: The text status from the T-1 scoring cycle to measure state changes.
    :type previous_status: Optional[str]
    :return: The aggregated and capped EnvironmentScore ready for database serialization.
    :rtype: EnvironmentScore
    """
    strike_interval = (
        settings.nifty_strike_interval
        if session_config.symbol == "NIFTY"
        else settings.sensex_strike_interval
    )

    # 1. Find single ATM row for Greek-heavy conditions (IV, Gamma/Theta, Move Ratio)
    atm = find_atm(option_chain, spot_price, strike_interval)

    # 2. Build multi-strike cluster for OI Flow and Trend Phases (ADR-012)
    cluster = build_strike_cluster(
        option_chain, 
        atm.atm_strike, 
        settings.oi_multi_strike_count,
        spot_price
    )

    # ── Run all 7 conditions ─────────────────────────────────────────────
    c1_iv = score_iv_change(iv_buffer, dte)
    c2_mom = score_momentum(candle_buffer)
    c3_oi = score_oi_flow(cluster, candle_buffer)
    c4_gt = score_gamma_theta(atm, dte)
    c5_pdhl = score_pdhl_breakout(spot_price, prev_levels)
    c6_move = score_move_ratio(atm, candle_buffer, dte)
    c7_vwap = score_vwap_distance(spot_price, candle_buffer)

    conditions = [c1_iv, c2_mom, c3_oi, c4_gt, c5_pdhl, c6_move, c7_vwap]

    # ── Compute total score ───────────────────────────────────────────────
    total_score = sum(c.points for c in conditions)
    max_score = sum(c.max_points for c in conditions)   # should be 8

    # ── IV contraction cap ────────────────────────────────────────────────
    iv_capped = c1_iv.status == "RED"

    # ── Determine final status ────────────────────────────────────────────
    status = _determine_status(total_score, iv_capped)

    # ── Build summary_raw ─────────────────────────────────────────────────
    summary_raw = _build_summary_raw(conditions, total_score, max_score, iv_capped, dte)

    return EnvironmentScore(
        timestamp=datetime.now(IST),
        symbol=session_config.symbol,
        expiry=session_config.expiry,
        dte=dte,
        score=total_score,
        max_score=max_score,
        status=status,
        iv_capped=iv_capped,
        total_ce_oi_change=cluster.total_ce_oi_change,
        total_pe_oi_change=cluster.total_pe_oi_change,
        conditions=conditions,
        summary_raw=summary_raw,
        previous_status=previous_status,
    )
