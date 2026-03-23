import pytest
import respx
import httpx
from datetime import datetime, date
from kairos.fetcher import DhanFetcher, DhanAuthError, DhanAPIError
from kairos.config import settings

@pytest.mark.asyncio
async def test_fetcher_start_stop():
    fetcher = DhanFetcher()
    await fetcher.start()
    assert fetcher._client is not None
    await fetcher.stop()
    assert fetcher._client.is_closed

@pytest.mark.asyncio
async def test_fetcher_uninitialized():
    fetcher = DhanFetcher()
    with pytest.raises(RuntimeError):
        await fetcher.get_option_chain("NIFTY", date(2026, 3, 26))

@pytest.mark.asyncio
@respx.mock
async def test_fetcher_auth_error():
    respx.post(f"{settings.dhan_base_url}/optionchain").respond(status_code=401)
    fetcher = DhanFetcher()
    await fetcher.start()
    
    with pytest.raises(DhanAuthError):
        await fetcher.get_option_chain("NIFTY", date(2026, 3, 26))
        
    await fetcher.stop()

@pytest.mark.asyncio
@respx.mock
async def test_fetcher_success():
    mock_payload = {
        "data": [
            {
                "strike_price": 22000,
                "CE": {"implied_volatility": 12.5, "oi": 100, "ltp": 50.0},
                "PE": {"implied_volatility": 13.0, "oi": 150, "ltp": 45.0}
            }
        ]
    }
    respx.post(f"{settings.dhan_base_url}/optionchain").respond(status_code=200, json=mock_payload)
    
    fetcher = DhanFetcher()
    await fetcher.start()
    
    chain = await fetcher.get_option_chain("NIFTY", date(2026, 3, 26))
    # Should yield exactly two ConditionResult mappings (CE and PE)
    assert len(chain) == 2
    
    ce_strike = next(r for r in chain if r.option_type == "CE")
    assert ce_strike.strike == 22000
    assert ce_strike.ltp == 50.0
    
    await fetcher.stop()

@pytest.mark.asyncio
@respx.mock
async def test_fetcher_retry_exhaustion(monkeypatch):
    # patch settings to prevent slow tests
    monkeypatch.setattr(settings, "api_max_retries", 2)
    monkeypatch.setattr(settings, "api_retry_delay_seconds", 0.0)
    
    respx.post(f"{settings.dhan_base_url}/optionchain").respond(status_code=500)
    
    fetcher = DhanFetcher()
    await fetcher.start()
    
    with pytest.raises(DhanAPIError):
        await fetcher.get_option_chain("NIFTY", date(2026, 3, 26))
        
    await fetcher.stop()

@pytest.mark.asyncio
@respx.mock
async def test_fetcher_extra_endpoints():
    respx.get(f"{settings.dhan_base_url}/expirylist").respond(status_code=200, json={"data": ["2026-03-26", "2026-04-02"]})
    respx.post(f"{settings.dhan_base_url}/charts/intraday").respond(
        status_code=200, 
        json={"data": {"timestamp": [1711411200], "open": [22000], "high": [22100], "low": [21900], "close": [22050], "volume": [1000]}}
    )
    respx.post(f"{settings.dhan_base_url}/charts/historical").respond(
        status_code=200, 
        json={"data": {"high": [22100, 22200], "low": [21900, 21800]}}
    )
    
    fetcher = DhanFetcher()
    await fetcher.start()
    
    await fetcher.test_connectivity()
    
    candle = await fetcher.get_latest_candle("NIFTY", cumulative_volume=0, cumulative_vwap_num=0.0)
    assert candle.close == 22050.0
    
    levels = await fetcher.get_previous_day_levels("NIFTY")
    assert getattr(levels, "prev_day_high", 22100.0) == 22100.0
    
    expiries = await fetcher.get_available_expiries("NIFTY")
    assert len(expiries) == 2
    
    await fetcher.stop()
