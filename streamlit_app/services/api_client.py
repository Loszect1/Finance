from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass(frozen=True)
class ApiConfig:
    base_url: str = "http://localhost:8000"
    timeout_seconds: int = 20


class ApiClient:
    def __init__(self, config: Optional[ApiConfig] = None) -> None:
        self.config = config or ApiConfig()

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.config.base_url.rstrip("/") + path

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = requests.get(self._url(path), params=params, timeout=self.config.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    # Convenience wrappers
    def health(self) -> Dict[str, Any]:
        return self.get_json("/health")

    def market_indices(self) -> Dict[str, Any]:
        return self.get_json("/api/market/indices")

    def top_movers(self, mover_type: str, universe: str = "VN30", limit: int = 10) -> Dict[str, Any]:
        return self.get_json(
            "/api/market/top-movers",
            params={"type": mover_type, "universe": universe, "limit": limit},
        )

    def price_board(self, universe: str = "VN30", limit: int = 200) -> Dict[str, Any]:
        return self.get_json("/api/market/price-board", params={"universe": universe, "limit": limit})

    def stocks_list(self, exchange: Optional[str] = None) -> Dict[str, Any]:
        params = {"exchange": exchange} if exchange else None
        return self.get_json("/api/stocks/list", params=params)

    def stock_quote(self, symbol: str) -> Dict[str, Any]:
        return self.get_json(f"/api/stock/{symbol}/quote")

    def stock_history(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        interval: str = "1D",
        length: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"interval": interval}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if length:
            params["length"] = length
        return self.get_json(f"/api/stock/{symbol}/history", params=params)

    def stock_profile(self, symbol: str) -> Dict[str, Any]:
        return self.get_json(f"/api/stock/{symbol}/profile")

    def stock_ratios(self, symbol: str, period: str = "year") -> Dict[str, Any]:
        return self.get_json(f"/api/stock/{symbol}/financial/ratios", params={"period": period})

    def stock_news(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        return self.get_json(f"/api/stock/{symbol}/news", params={"limit": limit})

    def news_latest(
        self,
        limit: int = 50,
        region: str = "vn",
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "region": region}
        if sources:
            params["sources"] = ",".join(sources)
        return self.get_json("/api/news/latest", params=params)

