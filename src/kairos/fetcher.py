"""
fetcher.py — All Dhan API interactions.
Returns typed Pydantic models. No business logic here.
All calls are async and use a shared httpx.AsyncClient.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from kairos.config import settings
from kairos.models import (
    AvailableExpiry,
    OHLCVCandle,
    OptionChainRow,
    PreviousDayLevels,
)

IST = ZoneInfo("Asia/Kolkata")


class DhanAPIError(Exception):
    """Raised when Dhan API returns an error or is unreachable."""
    pass


class DhanAuthError(DhanAPIError):
    """Raised on 401 — access token expired or invalid."""
    pass


class DhanFetcher:
    """
    Async Dhan API client.
    Uses a single shared httpx.AsyncClient across all calls.
    Create once at startup, close on shutdown.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Initialise the shared HTTP client. Call once at startup."""
        headers = {
            "client-id": settings.dhan_client_id,
            "Content-Type": "application/json",
        }
        if settings.dhan_access_token:
            headers["access-token"] = settings.dhan_access_token

        self._client = httpx.AsyncClient(
            base_url=settings.dhan_base_url,
            headers=headers,
            timeout=httpx.Timeout(10.0),
        )
        
        if not settings.dhan_access_token:
            await self._authenticate()
            
        logger.info("DhanFetcher: HTTP client initialised")

    async def _authenticate(self) -> None:
        """
        Dynamically fetch a new access token using Client ID, PIN, and TOTP secret.
        """
        if not settings.dhan_totp_secret or not settings.dhan_client_pin:
            raise DhanAuthError("Missing TOTP credentials to authenticate.")
            
        import pyotp
        totp_code = pyotp.TOTP(settings.dhan_totp_secret).now()
        
        auth_url = f"{settings.dhan_auth_url}/generateAccessToken"
        params = {
            "dhanClientId": settings.dhan_client_id,
            "pin": settings.dhan_client_pin,
            "totp": totp_code,
        }
        
        logger.info(f"Authenticating with DhanHQ: {params['dhanClientId']}")
        
        try:
            response = await self._client.post(auth_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                new_token = data.get("accessToken")
                if not new_token:
                    raise DhanAuthError(f"Authentication failed: No access token in response. Data: {data}")
                
                self._client.headers["access-token"] = new_token
                logger.info("Successfully fetched new Dhan access token via TOTP.")
            else:
                logger.error(f"Dhan auth failed with {response.status_code}: {response.text}")
                raise DhanAuthError(f"Dhan TOTP auth failed. Status: {response.status_code}")
                
        except httpx.RequestError as e:
            raise DhanAuthError(f"Network error during authentication: {e}")

    async def stop(self) -> None:
        """Close the shared HTTP client. Call on shutdown."""
        if self._client:
            await self._client.aclose()
            logger.info("DhanFetcher: HTTP client closed")

    def _check_client(self) -> None:
        if self._client is None:
            raise RuntimeError("DhanFetcher not started — call await fetcher.start() first")

    async def _get(self, endpoint: str, **kwargs) -> dict:
        """
        Internal GET with retry logic.
        Raises DhanAuthError on 401, DhanAPIError on other failures.
        """
        self._check_client()
        last_error: Exception = RuntimeError("No attempts made")

        for attempt in range(1, settings.api_max_retries + 1):
            try:
                response = await self._client.get(endpoint, **kwargs)

                if response.status_code == 401:
                    if settings.dhan_totp_secret and settings.dhan_client_pin:
                        logger.info("Received 401 Unauthorized. Attempting to re-authenticate with TOTP...")
                        await self._authenticate()
                        response = await self._client.get(endpoint, **kwargs)
                        if response.status_code == 401:
                            raise DhanAuthError("Dhan API auth failed (401) again after re-authentication")
                    else:
                        raise DhanAuthError("Dhan API auth failed (401) — access token may be expired")

                if response.status_code != 200:
                    logger.error(
                        f"[DHAN GET] {endpoint} → {response.status_code}\n"
                        f"  params: {kwargs.get('params', {})}\n"
                        f"  response body: {response.text[:500]}"
                    )
                    raise DhanAPIError(
                        f"Dhan API returned {response.status_code} for {endpoint}"
                    )

                return response.json()

            except DhanAuthError:
                raise   # auth errors don't retry

            except (httpx.TimeoutException, httpx.ConnectError, DhanAPIError) as e:
                last_error = e
                logger.warning(
                    f"DhanFetcher: attempt {attempt}/{settings.api_max_retries} "
                    f"failed for {endpoint}: {e}"
                )
                if attempt < settings.api_max_retries:
                    await asyncio.sleep(settings.api_retry_delay_seconds)

        raise DhanAPIError(
            f"Dhan API unreachable after {settings.api_max_retries} attempts: {last_error}"
        )

    async def _post(self, endpoint: str, payload: dict) -> dict:
        """
        Internal POST with retry logic.
        """
        self._check_client()
        last_error: Exception = RuntimeError("No attempts made")

        for attempt in range(1, settings.api_max_retries + 1):
            try:
                response = await self._client.post(endpoint, json=payload)

                if response.status_code == 401:
                    if settings.dhan_totp_secret and settings.dhan_client_pin:
                        logger.info("Received 401 Unauthorized. Attempting to re-authenticate with TOTP...")
                        await self._authenticate()
                        response = await self._client.post(endpoint, json=payload)
                        if response.status_code == 401:
                            raise DhanAuthError("Dhan API auth failed (401) again after re-authentication")
                    else:
                        raise DhanAuthError("Dhan API auth failed (401) — access token may be expired")

                if response.status_code != 200:
                    logger.error(
                        f"[DHAN POST] {endpoint} → {response.status_code}\n"
                        f"  payload: {payload}\n"
                        f"  response body: {response.text[:500]}"
                    )
                    raise DhanAPIError(
                        f"Dhan API returned {response.status_code} for {endpoint}"
                    )

                return response.json()

            except DhanAuthError:
                raise

            except (httpx.TimeoutException, httpx.ConnectError, DhanAPIError) as e:
                last_error = e
                logger.warning(
                    f"DhanFetcher: attempt {attempt}/{settings.api_max_retries} "
                    f"failed for {endpoint}: {e}"
                )
                if attempt < settings.api_max_retries:
                    await asyncio.sleep(settings.api_retry_delay_seconds)

        raise DhanAPIError(
            f"Dhan API unreachable after {settings.api_max_retries} attempts: {last_error}"
        )

    # ─────────────────────────────────────────────────────────────────────
    # Public fetch methods
    # ─────────────────────────────────────────────────────────────────────

    async def get_option_chain(
        self,
        symbol: str,
        expiry: date,
    ) -> list[OptionChainRow]:
        """
        Fetch the full option chain for a symbol+expiry.
        Returns all CE and PE strikes as OptionChainRow objects.
        Handles Dhan's `data.oc` nested structure.
        Dhan endpoint: POST /optionchain/

        """
        payload = {
            "UnderlyingScrip": 13,          # NIFTY scrip code
            "UnderlyingSeg": "IDX_I",
            "Expiry": expiry.strftime("%Y-%m-%d"),
        }

        if symbol == "SENSEX":
            payload["UnderlyingScrip"] = 51   # SENSEX scrip code
        elif symbol.isdigit():
            payload["UnderlyingScrip"] = int(symbol)

        data = await self._post("/optionchain", payload)
        now = datetime.now(IST)
        rows: list[OptionChainRow] = []

        # Dhan returns data.oc as dict keyed by strike price string
        oc = data.get("data", {}).get("oc", {})
        for strike_str, sides in oc.items():
            try:
                strike = int(float(strike_str))
            except (ValueError, TypeError):
                continue
            for opt_type, key in (("CE", "ce"), ("PE", "pe")):
                side = sides.get(key, {})
                if not side:
                    continue
                greeks = side.get("greeks", {})
                try:
                    rows.append(OptionChainRow(
                        timestamp=now,
                        symbol=symbol,
                        expiry=expiry,
                        strike=strike,
                        option_type=opt_type,
                        iv=float(side.get("implied_volatility", 0.0)),
                        delta=float(greeks.get("delta", 0.0)),
                        gamma=float(greeks.get("gamma", 0.0)),
                        theta=float(greeks.get("theta", 0.0)),
                        vega=float(greeks.get("vega", 0.0)),
                        oi=int(side.get("oi", 0)),
                        oi_change=int(side.get("oi", 0) - side.get("previous_oi", 0)),
                        volume=int(side.get("volume", 0)),
                        ltp=float(side.get("last_price", 0.0)),
                        bid=float(side.get("top_bid_price", 0.0)),
                        ask=float(side.get("top_ask_price", 0.0)),
                    ))
                except Exception as e:
                    logger.warning(f"Skipping malformed row for strike {strike_str}: {e}")
                    continue

        logger.debug(f"Fetched {len(rows)} option chain rows for {symbol} {expiry}")
        return rows

    async def get_latest_candle(
        self,
        symbol: str,
        cumulative_volume: int = 0,
        cumulative_vwap_num: float = 0.0,
    ) -> OHLCVCandle:
        """
        Fetch the latest 1-minute OHLCV candle for the underlying index.
        VWAP is calculated incrementally — caller passes cumulative values.
        Handles Dhan's root-level array response (timestamp, open, etc.).
        Dhan endpoint: POST /charts/intraday

        """
        security_id = 13    # NIFTY (integer, not string)
        if symbol == "SENSEX":
            security_id = 51
        elif symbol.isdigit():
            security_id = int(symbol)

        payload = {
            "securityId": security_id,
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX",
            "interval": "1",
            "oi": "false",
            "fromDate": date.today().strftime("%Y-%m-%d"),
            "toDate": date.today().strftime("%Y-%m-%d"),
        }

        logger.info(f"[INTRADAY] Requesting candle for securityId={security_id} date={date.today()}")
        data = await self._post("/charts/intraday", payload)
        # Dhan returns OHLCV arrays at root level (not nested under 'data')
        candles = data if "timestamp" in data else data.get("data", {})

        # Dhan returns arrays: timestamp, open, high, low, close, volume
        timestamps = candles.get("timestamp", [])
        opens = candles.get("open", [])
        highs = candles.get("high", [])
        lows = candles.get("low", [])
        closes = candles.get("close", [])
        volumes = candles.get("volume", [])

        logger.info(f"[INTRADAY] Candle count: {len(timestamps)}")
        if not timestamps:
            raise DhanAPIError(f"No candle data returned for {symbol}")

        # Use the last (most recent) candle
        idx = -1
        ts = datetime.fromtimestamp(timestamps[idx], tz=IST)
        o = float(opens[idx])
        h = float(highs[idx])
        lo = float(lows[idx])
        c = float(closes[idx])
        v = int(volumes[idx])

        # Incremental VWAP = cumulative(price * volume) / cumulative(volume)
        typical_price = (h + lo + c) / 3
        new_cum_vol = cumulative_volume + v
        new_cum_num = cumulative_vwap_num + (typical_price * v)
        vwap = new_cum_num / new_cum_vol if new_cum_vol > 0 else c

        return OHLCVCandle(
            timestamp=ts,
            symbol=symbol,
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=v,
            vwap=round(vwap, 2),
        )

    async def get_previous_day_levels(self, symbol: str) -> PreviousDayLevels:
        """
        Fetch previous trading day's high and low.
        Uses daily candle endpoint to get yesterday's data.
        Automatically detects whether today's candle is present to pick the correct index (-2 or -1).
        Dhan endpoint: POST /charts/historical

        """
        security_id = "13"
        if symbol == "SENSEX":
            security_id = "51"
        elif symbol.isdigit():
            security_id = symbol

        # Look back 7 days to ensure we cover weekends and holidays
        from_date = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        to_date = date.today().strftime("%Y-%m-%d")

        payload = {
            "securityId": security_id,
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX",
            "interval": "D",
            "oi": "false",
            "fromDate": from_date,
            "toDate": to_date,
        }

        data = await self._post("/charts/historical", payload)
        # Dhan returns OHLCV arrays at root level (same as intraday endpoint)
        candles = data if "high" in data else data.get("data", {})

        highs = candles.get("high", [])
        lows = candles.get("low", [])
        timestamps = candles.get("timestamp", [])

        if not highs:
            logger.warning("No historical data returned — PDH/PDL unavailable")
            pdh, pdl = 0.0, 0.0
        else:
            # Check if today's candle is included in the response
            # Timestamps are Unix epoch in IST; last entry might be today (partial) or yesterday (complete)
            last_ts = datetime.fromtimestamp(float(timestamps[-1]), tz=IST).date() if timestamps else None
            today_included = (last_ts == date.today())

            if today_included and len(highs) >= 2:
                # Today's partial candle is index -1 → use -2 for previous completed day
                idx = -2
            else:
                # Today not in response → last entry is the most recent completed trading day
                idx = -1

            pdh = float(highs[idx])
            pdl = float(lows[idx])

        logger.info(f"[HISTORICAL] PDH={pdh} | PDL={pdl}")

        return PreviousDayLevels(
            symbol=symbol,
            trade_date=date.today(),
            prev_day_high=pdh,
            prev_day_low=pdl,
            fetched_at=datetime.now(IST),
        )

    async def get_available_expiries(self, symbol: str) -> list[AvailableExpiry]:
        """
        Fetch list of available expiry dates for a symbol.
        Used to populate the Discord dropdown in /start-monitor.
        Dhan endpoint: GET /expirylist
        """
        security_id = "13"
        if symbol == "SENSEX":
            security_id = "51"
        elif symbol.isdigit():
            security_id = symbol

        # Dhan expirylist is a POST endpoint
        data = await self._post(
            "/optionchain/expirylist",
            payload={"UnderlyingScrip": int(security_id), "UnderlyingSeg": "IDX_I"},
        )

        expiries: list[AvailableExpiry] = []
        now = datetime.now(IST)

        for exp_str in data.get("data", []):
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                # Determine weekly vs monthly: last Thursday of month = monthly
                expiry_type = _classify_expiry(exp_date)
                expiries.append(AvailableExpiry(
                    symbol=symbol,
                    expiry=exp_date,
                    expiry_type=expiry_type,
                    fetched_at=now,
                ))
            except Exception as e:
                logger.warning(f"Could not parse expiry date {exp_str}: {e}")
                continue

        logger.info(f"Found {len(expiries)} expiries for {symbol}")
        return expiries

    async def test_connectivity(self) -> bool:
        """
        Lightweight connectivity test — used at startup health check.
        Returns True if Dhan API is reachable and credentials are valid.
        """
        try:
            await self._post("/optionchain/expirylist", payload={
                "UnderlyingScrip": 13,
                "UnderlyingSeg": "IDX_I",
            })
            return True
        except DhanAuthError:
            raise   # re-raise auth errors — these need immediate attention
        except DhanAPIError:
            return False


def _classify_expiry(exp_date: date) -> str:
    """
    Classify an expiry date as WEEKLY or MONTHLY.
    Monthly expiry = last Thursday of the month.
    """
    import calendar
    # Find last Thursday of the month
    year, month = exp_date.year, exp_date.month
    last_day = calendar.monthrange(year, month)[1]
    last_thursday = max(
        day for day in range(1, last_day + 1)
        if date(year, month, day).weekday() == 3  # 3 = Thursday
    )
    if exp_date.day == last_thursday:
        return "MONTHLY"
    return "WEEKLY"


# Module-level singleton
fetcher = DhanFetcher()
