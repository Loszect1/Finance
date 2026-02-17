from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from app.core.vnstock_compat import RateLimitException

from app.core.settings import settings
from app.services.news_service import news_service
from app.services.vnstock_service import (
    get_market_cards_cached,
    get_history_cached,
    get_price_board_cached,
    get_stock_list_cached,
    get_stock_news_cached,
    get_stock_quote_cached,
    get_top_movers_cached,
    init_vnstock,
    service,
)

load_dotenv()


logger = logging.getLogger("vnstock_monitor")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


def create_app() -> FastAPI:
    app = FastAPI(title="VN-Stock Monitor API", version="0.1.0")

    # CORS
    origins = [str(o) for o in settings.allowed_origins]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup() -> None:
        logger.info("Initializing vnstock configuration")
        init_vnstock()

    # ---------- Exception handlers ----------

    @app.exception_handler(RateLimitException)
    async def rate_limit_handler(_, exc: RateLimitException) -> JSONResponse:  # type: ignore[override]
        logger.warning("Rate limit exceeded: %s", exc)
        return JSONResponse(
            status_code=429,
            content={
                "detail": "vnstock rate limit exceeded. Please try again later or upgrade your plan.",
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_, exc: Exception) -> JSONResponse:  # type: ignore[override]
        logger.error("Unhandled error: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # ---------- Routes ----------

    @app.get("/health", tags=["system"])
    async def health_check() -> Dict[str, Any]:
        return {"status": "ok"}

    @app.get("/api/market/indices", tags=["market"])
    async def get_market_indices() -> Dict[str, Any]:
        """Market overview cards based on VN30/HNX30 proxies."""
        cards = get_market_cards_cached()
        series = get_history_cached(symbol="VNINDEX", start=None, end=None, interval="1D", length="1M")
        if not series:
            series = get_history_cached(symbol="VN30", start=None, end=None, interval="1D", length="1M")
        return {"cards": cards, "series": series}

    @app.get("/api/market/price-board", tags=["market"])
    async def get_price_board(
        universe: str = Query("VN30"),
        limit: int = Query(200, ge=1, le=500),
    ) -> Dict[str, Any]:
        try:
            items = get_price_board_cached(universe=universe, limit=limit)
        except RateLimitException as exc:
            raise exc
        except Exception as exc:
            logger.error("Failed to load price board: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to load price board")
        return {"items": items}

    @app.get("/api/market/top-movers", tags=["market"])
    async def get_top_movers(
        type: str = Query("gainers", pattern="^(gainers|losers|volume)$"),
        universe: str = Query("VN30"),
        limit: int = Query(10, ge=1, le=50),
    ) -> Dict[str, Any]:
        try:
            movers = get_top_movers_cached(mover_type=type, universe=universe, limit=limit)
        except RateLimitException as exc:
            raise exc
        except Exception as exc:
            logger.error("Failed to get top movers: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to load top movers")
        return {"items": movers}

    @app.get("/api/stocks/list", tags=["stocks"])
    async def list_stocks(
        exchange: str | None = Query(None, pattern="^(HOSE|HNX|UPCOM)$"),
    ) -> Dict[str, Any]:
        try:
            items = get_stock_list_cached(exchange=exchange)
        except Exception as exc:
            logger.error("Failed to list stocks: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to load stock list")
        return {"items": items}

    @app.get("/api/stock/{symbol}/quote", tags=["stocks"])
    async def stock_quote(symbol: str) -> Dict[str, Any]:
        try:
            data = get_stock_quote_cached(symbol=symbol.upper())
        except RateLimitException as exc:
            raise exc
        except Exception as exc:
            logger.error("Failed to load quote for %s: %s", symbol, exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to load quote for {symbol}")

        if not data:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        return data

    @app.get("/api/stock/{symbol}/history", tags=["stocks"])
    async def stock_history(
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        interval: str = "1D",
        length: str | None = None,
    ) -> Dict[str, Any]:
        try:
            items = get_history_cached(
                symbol=symbol.upper(),
                start=start,
                end=end,
                interval=interval,
                length=length,
            )
        except RateLimitException as exc:
            raise exc
        except Exception as exc:
            logger.error("Failed to load history for %s: %s", symbol, exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to load history for {symbol}")

        return {"items": items}

    @app.get("/api/stock/{symbol}/profile", tags=["stocks"])
    async def stock_profile(symbol: str) -> Dict[str, Any]:
        try:
            data = service.company_overview(symbol=symbol.upper())
        except Exception as exc:
            logger.error("Failed to load profile for %s: %s", symbol, exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to load profile for {symbol}")

        if not data:
            raise HTTPException(status_code=404, detail=f"Profile for {symbol} not found")
        return data

    @app.get("/api/stock/{symbol}/financial/ratios", tags=["stocks"])
    async def stock_financial_ratios(
        symbol: str,
        period: str = Query("year", pattern="^(year|quarter)$"),
    ) -> Dict[str, Any]:
        try:
            items = service.financial_ratios(symbol=symbol.upper(), period=period)
        except Exception as exc:
            logger.error("Failed to load financial ratios for %s: %s", symbol, exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load financial ratios for {symbol}",
            )
        return {"items": items}

    @app.get("/api/stock/{symbol}/news", tags=["news"])
    async def stock_news(symbol: str, limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
        try:
            items = get_stock_news_cached(symbol=symbol.upper(), limit=limit)
        except RateLimitException as exc:
            raise exc
        except Exception as exc:
            logger.error("Failed to load news for %s: %s", symbol, exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to load news for {symbol}")
        return {"items": items}

    @app.get("/api/news/latest", tags=["news"])
    async def latest_news(
        limit: int = Query(50, ge=1, le=200),
        region: str = Query("vn", pattern="^(vn|global|all)$"),
        sources: str | None = Query(None),
    ) -> Dict[str, Any]:
        """Multi-source news feed (VN + global)."""
        try:
            source_list = [s.strip().lower() for s in (sources.split(",") if sources else []) if s.strip()]
            items = await news_service.latest(region=region, sources=source_list or None, limit=limit)
        except Exception as exc:
            logger.error("Failed to load latest news: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to load latest news")
        return {"items": items}

    return app


app = create_app()

