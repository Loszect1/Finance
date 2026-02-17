from __future__ import annotations

import os
from typing import Optional

import pandas as pd
import streamlit as st

from services.api_client import ApiClient, ApiConfig
from components.header import render_header
from components.theme import inject_theme_css


st.set_page_config(page_title="Market - VN-Stock Monitor", layout="wide")
inject_theme_css()

base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
api = ApiClient(ApiConfig(base_url=base_url))

render_header(api)
st.divider()
st.markdown("## Danh sách thị trường")

view_labels = {
    "Price board": "Bảng giá",
    "Listing": "Danh sách niêm yết",
}
view = st.selectbox(
    "Chế độ xem",
    options=list(view_labels.keys()),
    index=0,
    format_func=lambda x: view_labels.get(x, x),
)

if view == "Price board":
    universe = st.selectbox(
        "Rổ / Sàn giao dịch",
        options=["VN30", "VN100", "HNX30", "HOSE", "HNX", "UPCOM"],
        index=0,
    )
    limit = st.slider("Số dòng tối đa hiển thị", min_value=20, max_value=500, value=200, step=20)
    try:
        res = api.price_board(universe=universe, limit=limit)
        df = pd.DataFrame(res.get("items", []))
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Không tải được bảng giá: {e}")
else:
    exchange = st.selectbox("Sàn giao dịch", options=["", "HOSE", "HNX", "UPCOM"], index=0)
    try:
        res = api.stocks_list(exchange=exchange or None)
        df = pd.DataFrame(res.get("items", []))

        # Optionally enrich with realtime quote data when an exchange is selected
        if exchange:
            try:
                board_res = api.price_board(universe=exchange, limit=500)
                board_df = pd.DataFrame(board_res.get("items", []))
                if not board_df.empty and "symbol" in board_df.columns:
                    quote_cols = [
                        "symbol",
                        "close_price" if "close_price" in board_df.columns else "match_price",
                        "reference_price" if "reference_price" in board_df.columns else "ref_price",
                        "pct_change" if "pct_change" in board_df.columns else None,
                    ]
                    quote_cols = [c for c in quote_cols if c and c in board_df.columns]
                    board_small = board_df[quote_cols].copy()
                    df = df.merge(board_small, on="symbol", how="left")
            except Exception:
                # If enrichment fails, fall back to listing-only view
                pass

        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Không tải được danh sách mã: {e}")

