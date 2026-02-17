from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from vnstock import Company, Finance, Listing, Quote, Trading

from app.core.cache import ttl_cache
from app.core.settings import settings
from app.core.vnstock_compat import RateLimitException, get_set_api_key


def init_vnstock() -> None:
    """Configure vnstock with API key if provided."""
    api_key = settings.vnstok_api_key or ""
    if not api_key:
        return
    setter = get_set_api_key()
    if setter:
        setter(api_key)


@dataclass
class QuoteCard:
    name: str
    proxy_group: str
    value: float
    change: float
    pct_change: float
    as_of: str


class VnstockService:
    """Wrapper around vnstock with source fallback and safe JSON outputs."""

    def __init__(self, primary_source: str = "kbs", fallback_source: str = "vci") -> None:
        self.primary_source = primary_source.lower()
        self.fallback_source = fallback_source.lower()

    # ---------- Helpers ----------

    @staticmethod
    def _df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
        if df is None:
            return []
        if not isinstance(df, pd.DataFrame):
            return []
        return df.to_dict(orient="records")

    @staticmethod
    def _safe_time(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    # ---------- Listing ----------

    def list_symbols(
        self,
        exchange: Optional[str] = None,
        to_df: bool = False,
    ) -> Any:
        """List all symbols, optionally filtered by exchange."""
        try:
            listing = Listing(source=self.primary_source)
        except ValueError:
            listing = Listing(source=self.fallback_source)

        if exchange:
            df = listing.symbols_by_exchange(exchange=exchange.upper(), to_df=True)
        else:
            df = listing.all_symbols(to_df=True)

        if to_df:
            return df
        return self._df_to_records(df)

    # ---------- Market cards / indices proxies ----------

    def market_cards_from_groups(
        self,
        groups: Sequence[str],
        exchange: str = "HOSE",
    ) -> List[QuoteCard]:
        """Compute simple index-like cards from group constituents using price_board."""
        cards: List[QuoteCard] = []
        now = datetime.utcnow().isoformat()

        for group in groups:
            try:
                listing = Listing(source=self.primary_source)
            except ValueError:
                listing = Listing(source=self.fallback_source)

            # vnstock may return a list/tuple/Series depending on version.
            raw_symbols = listing.symbols_by_group(group_name=group, to_df=False)
            if raw_symbols is None:
                continue

            # Normalize to a simple Python list and guard against pandas Series ambiguity.
            try:
                symbols_list = list(raw_symbols)
            except TypeError:
                # Unexpected type – skip this group instead of breaking the whole endpoint.
                continue

            if len(symbols_list) == 0:
                continue

            try:
                trading = Trading(source=self.primary_source)
            except ValueError:
                trading = Trading(source=self.fallback_source)

            try:
                board = trading.price_board(symbols_list=symbols_list)
            except Exception:
                cards.append(
                    QuoteCard(
                        name=group,
                        proxy_group=group,
                        value=0,
                        change=0,
                        pct_change=0,
                        as_of=now,
                    )
                )
                continue

            if board.empty:
                continue

            # Use reference_price as base, close_price/last as proxy; fall back gracefully
            ref_col = "reference_price" if "reference_price" in board.columns else "ref_price"
            last_col = "close_price" if "close_price" in board.columns else "match_price"

            ref_mean = float(board[ref_col].mean())
            last_mean = float(board[last_col].mean())
            change = last_mean - ref_mean
            pct = (change / ref_mean * 100) if ref_mean else 0.0

            cards.append(
                QuoteCard(
                    name=group,
                    proxy_group=group,
                    value=round(last_mean, 2),
                    change=round(change, 2),
                    pct_change=round(pct, 2),
                    as_of=now,
                )
            )

        return cards

    # ---------- Top movers ----------

    def top_movers(
        self,
        mover_type: str,
        universe: str = "VN30",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Compute top movers using price_board data."""
        mover_type = mover_type.lower()

        try:
            listing = Listing(source=self.primary_source)
        except ValueError:
            listing = Listing(source=self.fallback_source)

        symbols: Sequence[str]
        if universe.upper() in ("VN30", "VN100", "HNX30"):
            symbols = listing.symbols_by_group(group_name=universe.upper(), to_df=False)
        elif universe.upper() in ("HOSE", "HNX", "UPCOM"):
            df = listing.symbols_by_exchange(exchange=universe.upper(), to_df=True)
            symbols = list(df["symbol"].tolist())
        else:
            df = listing.all_symbols(to_df=True)
            symbols = list(df["symbol"].tolist())

        symbols = list(symbols)[:200]  # hard cap for safety
        if not symbols:
            return []

        try:
            trading = Trading(source=self.primary_source)
        except ValueError:
            trading = Trading(source=self.fallback_source)

        try:
            board = trading.price_board(symbols_list=list(symbols))
        except Exception:
            return []

        if board.empty:
            return []

        # Standardized columns
        ref_col = "reference_price" if "reference_price" in board.columns else "ref_price"
        last_col = "close_price" if "close_price" in board.columns else "match_price"

        board = board.copy()
        board["change"] = board[last_col] - board[ref_col]
        board["pct_change"] = board["change"] / board[ref_col] * 100

        if mover_type == "gainers":
            df_sorted = board.sort_values("pct_change", ascending=False)
        elif mover_type == "losers":
            df_sorted = board.sort_values("pct_change", ascending=True)
        else:  # volume
            vol_col = "total_trades" if "total_trades" in board.columns else "total_volume"
            df_sorted = board.sort_values(vol_col, ascending=False)

        cols = ["symbol", ref_col, last_col, "change", "pct_change"]
        keep = [c for c in cols if c in df_sorted.columns]
        result = df_sorted[keep].head(limit)
        return self._df_to_records(result)

    def price_board(
        self,
        universe: str = "VN30",
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Get realtime price board for a universe (group or exchange)."""
        universe_u = universe.upper()
        limit = max(1, min(int(limit), 500))

        try:
            listing = Listing(source=self.primary_source)
        except ValueError:
            listing = Listing(source=self.fallback_source)

        symbols: List[str] = []
        if universe_u in ("VN30", "VN100", "HNX30"):
            symbols = list(listing.symbols_by_group(group_name=universe_u, to_df=False))
        elif universe_u in ("HOSE", "HNX", "UPCOM"):
            df = listing.symbols_by_exchange(exchange=universe_u, to_df=True)
            if "symbol" in df.columns:
                symbols = list(df["symbol"].tolist())
        else:
            df = listing.all_symbols(to_df=True)
            if "symbol" in df.columns:
                symbols = list(df["symbol"].tolist())

        symbols = symbols[:limit]
        if not symbols:
            return []

        # Chunk requests for safety
        def chunks(seq: List[str], size: int) -> List[List[str]]:
            return [seq[i : i + size] for i in range(0, len(seq), size)]

        last_error: Optional[Exception] = None
        for source in (self.primary_source, self.fallback_source):
            try:
                trading = Trading(source=source)
                frames: List[pd.DataFrame] = []
                for batch in chunks(symbols, 50):
                    frames.append(trading.price_board(symbols_list=batch))
                board = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
                records = self._df_to_records(board)
                for r in records:
                    r["source"] = source
                return records
            except RateLimitException:
                raise
            except Exception as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error
        return []

    # ---------- Quote / history ----------

    def quote_history(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        interval: str = "1D",
        length: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get OHLCV history with KBS primary, VCI fallback."""
        for source in (self.primary_source, self.fallback_source):
            try:
                quote = Quote(source=source, symbol=symbol)
                kwargs: Dict[str, Any] = {"interval": interval}
                if start:
                    kwargs["start"] = start
                if end:
                    kwargs["end"] = end
                if length:
                    kwargs["length"] = length
                df = quote.history(**kwargs)
                if df is not None and not df.empty:
                    return self._df_to_records(df)
            except RateLimitException:
                raise
            except Exception:
                continue
        return []

    # ---------- Stock quote ----------

    def stock_quote(self, symbol: str) -> Dict[str, Any]:
        """Get realtime quote for a single symbol from price_board."""
        last_error: Optional[Exception] = None

        for source in (self.primary_source, self.fallback_source):
            try:
                trading = Trading(source=source)
                df = trading.price_board(symbols_list=[symbol])
                if df is None or df.empty:
                    continue
                record = self._df_to_records(df)[0]
                record["source"] = source
                return record
            except RateLimitException:
                raise
            except Exception as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error
        return {}

    # ---------- Company / Finance ----------

    def company_overview(self, symbol: str) -> Dict[str, Any]:
        for source in (self.primary_source, self.fallback_source):
            try:
                company = Company(source=source, symbol=symbol)
                df = company.overview()
                records = self._df_to_records(df)
                if records:
                    return records[0]
            except Exception:
                continue
        return {}

    def financial_ratios(self, symbol: str, period: str = "year") -> List[Dict[str, Any]]:
        for source in (self.primary_source, self.fallback_source):
            try:
                finance = Finance(source=source, symbol=symbol)
                df = finance.ratio(period=period)
                if df is not None and not df.empty:
                    return self._df_to_records(df)
            except Exception:
                continue
        return []

    # ---------- Company news ----------

    def company_news(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        for source in (self.primary_source, self.fallback_source):
            try:
                company = Company(source=source, symbol=symbol)
                df = company.news()
                if df is None or df.empty:
                    continue
                records = self._df_to_records(df)
                return records[:limit]
            except Exception:
                continue
        return []


service = VnstockService()


def get_market_cards_cached() -> List[Dict[str, Any]]:
    """Cached wrapper for dashboard market cards."""

    def _build() -> List[Dict[str, Any]]:
        cards = service.market_cards_from_groups(groups=["VN30", "HNX30"])
        return [asdict(c) for c in cards]

    cache_key = "market_cards_vn30_hnx30"
    cached = ttl_cache.get(cache_key)
    if cached is not None:
        return cached
    result = _build()
    ttl_cache.set(cache_key, result, ttl_seconds=60)
    return result


def get_stock_list_cached(exchange: Optional[str]) -> List[Dict[str, Any]]:
    cache_key = f"stocks_list:{(exchange or 'ALL').upper()}"
    cached = ttl_cache.get(cache_key)
    if cached is not None:
        return cached
    items = service.list_symbols(exchange=exchange, to_df=False)
    ttl_cache.set(cache_key, items, ttl_seconds=60 * 60 * 12)
    return items


def get_top_movers_cached(mover_type: str, universe: str, limit: int) -> List[Dict[str, Any]]:
    cache_key = f"top_movers:{mover_type}:{universe}:{limit}"
    cached = ttl_cache.get(cache_key)
    if cached is not None:
        return cached
    items = service.top_movers(mover_type=mover_type, universe=universe, limit=limit)
    ttl_cache.set(cache_key, items, ttl_seconds=60)
    return items


def get_stock_quote_cached(symbol: str) -> Dict[str, Any]:
    cache_key = f"stock_quote:{symbol.upper()}"
    cached = ttl_cache.get(cache_key)
    if cached is not None:
        return cached
    item = service.stock_quote(symbol=symbol.upper())
    ttl_cache.set(cache_key, item, ttl_seconds=15)
    return item


def get_history_cached(
    symbol: str,
    start: Optional[str],
    end: Optional[str],
    interval: str,
    length: Optional[str],
) -> List[Dict[str, Any]]:
    cache_key = f"history:{symbol.upper()}:{start or ''}:{end or ''}:{interval}:{length or ''}"
    cached = ttl_cache.get(cache_key)
    if cached is not None:
        return cached
    items = service.quote_history(
        symbol=symbol.upper(),
        start=start,
        end=end,
        interval=interval,
        length=length,
    )
    ttl_cache.set(cache_key, items, ttl_seconds=120)
    return items


def get_price_board_cached(universe: str, limit: int) -> List[Dict[str, Any]]:
    cache_key = f"price_board:{universe.upper()}:{limit}"
    cached = ttl_cache.get(cache_key)
    if cached is not None:
        return cached
    items = service.price_board(universe=universe, limit=limit)
    ttl_cache.set(cache_key, items, ttl_seconds=15)
    return items


def get_stock_news_cached(symbol: str, limit: int) -> List[Dict[str, Any]]:
    """Cached wrapper for company news endpoint."""
    symbol_u = symbol.upper()
    cache_key = f"stock_news:{symbol_u}:{limit}"
    cached = ttl_cache.get(cache_key)
    if cached is not None:
        return cached
    items = service.company_news(symbol=symbol_u, limit=limit)
    ttl_cache.set(cache_key, items, ttl_seconds=600)
    return items

