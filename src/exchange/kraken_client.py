"""
Kraken API Client
=================
Lightweight client for fetching market data from Kraken.
Adapted from BitcoinBot for the trading-system project.

Features:
- Rate limiting (1s between calls)
- Exponential backoff for transient errors
- OHLCV, ticker, spread data
- No database dependencies
"""

import os
import time
import logging
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta

try:
    import krakenex
    from pykrakenapi import KrakenAPI
    KRAKEN_AVAILABLE = True
except ImportError:
    KRAKEN_AVAILABLE = False

from dotenv import load_dotenv

log = logging.getLogger(__name__)


@dataclass
class TickerData:
    """Ticker information for a trading pair."""
    pair: str
    ask: Decimal
    bid: Decimal
    last: Decimal
    volume_24h: Decimal
    vwap_24h: Decimal
    high_24h: Decimal
    low_24h: Decimal
    spread: Decimal
    spread_pct: Decimal
    timestamp: datetime


@dataclass
class OHLCVBar:
    """Single OHLCV candlestick."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    vwap: Decimal
    volume: Decimal
    count: int


@dataclass
class AssetInfo:
    """Asset information."""
    name: str
    altname: str
    decimals: int
    display_decimals: int


class KrakenClient:
    """
    Kraken API client for market data.

    Usage:
        client = KrakenClient()  # Uses .env for credentials
        ticker = client.get_ticker("BTC/USD")
        ohlcv = client.get_ohlcv("BTC/USD", interval=60, limit=100)
    """

    # Kraken pair name mapping (internal -> API)
    PAIR_MAP = {
        "BTC/USD": "XXBTZUSD",
        "ETH/USD": "XETHZUSD",
        "SOL/USD": "SOLUSD",
        "XRP/USD": "XXRPZUSD",
        "ADA/USD": "ADAUSD",
        "DOT/USD": "DOTUSD",
        "LINK/USD": "LINKUSD",
        "AVAX/USD": "AVAXUSD",
        "MATIC/USD": "MATICUSD",
        "ATOM/USD": "ATOMUSD",
    }

    # Reverse mapping
    PAIR_MAP_REVERSE = {v: k for k, v in PAIR_MAP.items()}

    # Transient errors that should trigger retry
    TRANSIENT_ERRORS = [
        'EAPI:Rate limit exceeded',
        'EService:Unavailable',
        'EService:Busy',
        'EGeneral:Temporary lockout',
        'timeout',
        'timed out',
        'Connection reset',
        'Connection refused',
    ]

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize Kraken client.

        Args:
            api_key: Kraken API key (or set KRAKEN_API_KEY env var)
            api_secret: Kraken API secret (or set KRAKEN_API_SECRET env var)
        """
        if not KRAKEN_AVAILABLE:
            raise ImportError(
                "krakenex and pykrakenapi required. "
                "Install with: pip install krakenex pykrakenapi python-dotenv"
            )

        load_dotenv()

        self.api_key = api_key or os.getenv('KRAKEN_API_KEY')
        self.api_secret = api_secret or os.getenv('KRAKEN_API_SECRET')

        # Initialize API (works without credentials for public endpoints)
        if self.api_key and self.api_secret:
            self.api = krakenex.API(key=self.api_key, secret=self.api_secret)
        else:
            self.api = krakenex.API()
            log.warning("No API credentials - only public endpoints available")

        self.kapi = KrakenAPI(self.api)
        self.last_call = 0
        self.min_interval = 1.0  # seconds between calls

        # Cache for expensive operations
        self._ticker_cache: Dict[str, Tuple[TickerData, float]] = {}
        self._cache_ttl = 5.0  # seconds

    def _to_api_pair(self, pair: str) -> str:
        """Convert friendly pair name to Kraken API pair name."""
        return self.PAIR_MAP.get(pair, pair)

    def _from_api_pair(self, api_pair: str) -> str:
        """Convert Kraken API pair name to friendly name."""
        return self.PAIR_MAP_REVERSE.get(api_pair, api_pair)

    def _is_transient_error(self, error_msg: str) -> bool:
        """Check if error is transient and should trigger retry."""
        error_lower = str(error_msg).lower()
        return any(pattern.lower() in error_lower for pattern in self.TRANSIENT_ERRORS)

    def _rate_limit(self):
        """Enforce minimum interval between API calls."""
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()

    def _call_with_retry(self, func, *args, max_retries: int = 3, **kwargs):
        """Execute API call with exponential backoff for transient errors."""
        last_error = None

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                last_error = e
                if self._is_transient_error(str(e)):
                    backoff = 2 ** attempt
                    log.warning(f"Transient error (attempt {attempt+1}/{max_retries}): {e}, "
                               f"backing off {backoff}s")
                    time.sleep(backoff)
                    continue
                raise

        raise last_error

    def get_ticker(self, pair: str, use_cache: bool = True) -> Optional[TickerData]:
        """
        Get current ticker for a pair.

        Args:
            pair: Trading pair (e.g., "BTC/USD")
            use_cache: Use cached data if available and fresh

        Returns:
            TickerData or None on error
        """
        # Check cache
        if use_cache and pair in self._ticker_cache:
            cached, cached_time = self._ticker_cache[pair]
            if time.time() - cached_time < self._cache_ttl:
                return cached

        api_pair = self._to_api_pair(pair)

        try:
            df = self._call_with_retry(self.kapi.get_ticker_information, api_pair)

            if df is None or df.empty:
                log.error(f"No ticker data for {pair}")
                return None

            row = df.iloc[0]

            ask = Decimal(str(row['a'][0]))
            bid = Decimal(str(row['b'][0]))
            last = Decimal(str(row['c'][0]))
            spread = ask - bid
            spread_pct = (spread / last * 100) if last > 0 else Decimal("0")

            ticker = TickerData(
                pair=pair,
                ask=ask,
                bid=bid,
                last=last,
                volume_24h=Decimal(str(row['v'][1])),
                vwap_24h=Decimal(str(row['p'][1])),
                high_24h=Decimal(str(row['h'][1])),
                low_24h=Decimal(str(row['l'][1])),
                spread=spread,
                spread_pct=spread_pct,
                timestamp=datetime.now()
            )

            # Update cache
            self._ticker_cache[pair] = (ticker, time.time())

            return ticker

        except Exception as e:
            log.error(f"Failed to get ticker for {pair}: {e}")
            return None

    def get_ohlcv(
        self,
        pair: str,
        interval: int = 60,
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[OHLCVBar]:
        """
        Get OHLCV candlestick data.

        Args:
            pair: Trading pair (e.g., "BTC/USD")
            interval: Candle interval in minutes (1, 5, 15, 30, 60, 240, 1440, 10080, 21600)
            limit: Maximum number of candles to return
            since: Unix timestamp to start from (optional)

        Returns:
            List of OHLCVBar objects (oldest first)
        """
        api_pair = self._to_api_pair(pair)

        try:
            result = self._call_with_retry(
                self.kapi.get_ohlc_data,
                api_pair,
                interval=interval,
                since=since
            )

            if result is None:
                return []

            # pykrakenapi returns (DataFrame, last_id) tuple
            df = result[0] if isinstance(result, tuple) else result

            if df is None or df.empty:
                return []

            bars = []
            for idx, row in df.iterrows():
                bar = OHLCVBar(
                    timestamp=idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                    open=Decimal(str(row['open'])),
                    high=Decimal(str(row['high'])),
                    low=Decimal(str(row['low'])),
                    close=Decimal(str(row['close'])),
                    vwap=Decimal(str(row['vwap'])),
                    volume=Decimal(str(row['volume'])),
                    count=int(row['count'])
                )
                bars.append(bar)

            # Return only the requested limit (most recent)
            return bars[-limit:] if len(bars) > limit else bars

        except Exception as e:
            log.error(f"Failed to get OHLCV for {pair}: {e}")
            return []

    def get_spread(self, pair: str) -> Optional[Decimal]:
        """
        Get current spread for a pair as a percentage.

        Args:
            pair: Trading pair (e.g., "BTC/USD")

        Returns:
            Spread as decimal percentage (e.g., 0.0005 for 0.05%)
        """
        ticker = self.get_ticker(pair)
        if ticker:
            return ticker.spread_pct / 100
        return None

    def get_24h_volume(self, pair: str) -> Optional[Decimal]:
        """
        Get 24-hour trading volume in base currency.

        Args:
            pair: Trading pair (e.g., "BTC/USD")

        Returns:
            24h volume or None on error
        """
        ticker = self.get_ticker(pair)
        if ticker:
            return ticker.volume_24h
        return None

    def get_multiple_tickers(self, pairs: List[str]) -> Dict[str, TickerData]:
        """
        Get tickers for multiple pairs.

        Args:
            pairs: List of trading pairs

        Returns:
            Dict mapping pair -> TickerData
        """
        results = {}
        for pair in pairs:
            ticker = self.get_ticker(pair)
            if ticker:
                results[pair] = ticker
        return results

    def get_historical_prices(self, pair: str, days: int = 60) -> List[Decimal]:
        """
        Get daily closing prices for the past N days.

        Args:
            pair: Trading pair
            days: Number of days of history

        Returns:
            List of closing prices (oldest first)
        """
        # Use daily candles (1440 minutes)
        bars = self.get_ohlcv(pair, interval=1440, limit=days + 1)
        return [bar.close for bar in bars]

    def get_historical_volumes(self, pair: str, days: int = 60) -> List[Decimal]:
        """
        Get daily volumes for the past N days.

        Args:
            pair: Trading pair
            days: Number of days of history

        Returns:
            List of daily volumes (oldest first)
        """
        bars = self.get_ohlcv(pair, interval=1440, limit=days + 1)
        return [bar.volume for bar in bars]

    def calculate_atr(self, pair: str, period: int = 14) -> Optional[Decimal]:
        """
        Calculate Average True Range for a pair.

        Args:
            pair: Trading pair
            period: ATR period (default 14)

        Returns:
            ATR as decimal or None on error
        """
        bars = self.get_ohlcv(pair, interval=1440, limit=period + 1)

        if len(bars) < period + 1:
            log.warning(f"Not enough data for ATR calculation: {len(bars)} bars")
            return None

        true_ranges = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        atr = sum(true_ranges[-period:]) / Decimal(period)
        return atr

    def calculate_volatility_pct(self, pair: str, period: int = 14) -> Optional[Decimal]:
        """
        Calculate volatility as ATR percentage of price.

        Args:
            pair: Trading pair
            period: Lookback period

        Returns:
            Volatility as percentage (e.g., 5.0 for 5%)
        """
        atr = self.calculate_atr(pair, period)
        ticker = self.get_ticker(pair)

        if atr and ticker and ticker.last > 0:
            return (atr / ticker.last) * 100
        return None

    def get_tradeable_pairs(self) -> List[str]:
        """
        Get list of tradeable USD pairs on Kraken.

        Returns:
            List of pair names (e.g., ["BTC/USD", "ETH/USD", ...])
        """
        try:
            result = self._call_with_retry(self.api.query_public, 'AssetPairs')

            if result.get('error'):
                log.error(f"Failed to get asset pairs: {result['error']}")
                return list(self.PAIR_MAP.keys())

            pairs = []
            for pair_name, info in result.get('result', {}).items():
                # Filter for USD quote pairs
                if pair_name.endswith('USD') or pair_name.endswith('ZUSD'):
                    # Convert to friendly name if known
                    friendly = self._from_api_pair(pair_name)
                    if '/' not in friendly:
                        # Create friendly name from API name
                        base = pair_name.replace('USD', '').replace('ZUSD', '')
                        base = base.replace('XX', '').replace('XZ', '').replace('X', '')
                        friendly = f"{base}/USD"
                    pairs.append(friendly)

            return sorted(set(pairs))

        except Exception as e:
            log.error(f"Failed to get tradeable pairs: {e}")
            return list(self.PAIR_MAP.keys())

    def get_balance(self) -> Optional[Dict[str, Decimal]]:
        """
        Get account balance (requires API credentials).

        Returns:
            Dict mapping asset -> balance, or None on error
        """
        if not self.api_key or not self.api_secret:
            log.error("API credentials required for balance query")
            return None

        try:
            df = self._call_with_retry(self.kapi.get_account_balance)

            if df is None or df.empty:
                return {}

            balances = {}
            for asset, row in df.iterrows():
                balance = Decimal(str(row['vol']))
                if balance > 0:
                    balances[asset] = balance

            return balances

        except Exception as e:
            log.error(f"Failed to get balance: {e}")
            return None

    def health_check(self) -> bool:
        """
        Check if Kraken API is accessible.

        Returns:
            True if API is working, False otherwise
        """
        try:
            result = self._call_with_retry(self.api.query_public, 'Time')
            return 'error' not in result or not result['error']
        except Exception as e:
            log.error(f"Health check failed: {e}")
            return False


# Convenience function for quick data fetching
def fetch_market_data(pairs: List[str]) -> Dict[str, TickerData]:
    """
    Fetch market data for multiple pairs.

    Args:
        pairs: List of trading pairs

    Returns:
        Dict mapping pair -> TickerData
    """
    client = KrakenClient()
    return client.get_multiple_tickers(pairs)


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(level=logging.INFO)

    print("Kraken Client Demo")
    print("=" * 60)

    client = KrakenClient()

    # Health check
    print(f"\nAPI Health: {'OK' if client.health_check() else 'FAILED'}")

    # Get ticker
    print("\n--- Ticker Data ---")
    for pair in ["BTC/USD", "ETH/USD", "SOL/USD"]:
        ticker = client.get_ticker(pair)
        if ticker:
            print(f"{pair}: ${ticker.last:,.2f} (spread: {ticker.spread_pct:.4f}%)")

    # Get volatility
    print("\n--- Volatility (14D ATR%) ---")
    for pair in ["BTC/USD", "ETH/USD"]:
        vol = client.calculate_volatility_pct(pair)
        if vol:
            print(f"{pair}: {vol:.2f}%")

    # Get OHLCV sample
    print("\n--- Recent OHLCV (BTC/USD, 1H) ---")
    bars = client.get_ohlcv("BTC/USD", interval=60, limit=5)
    for bar in bars[-3:]:
        print(f"  {bar.timestamp}: O={bar.open} H={bar.high} L={bar.low} C={bar.close}")
