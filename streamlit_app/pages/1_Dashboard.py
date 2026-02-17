from __future__ import annotations

import os
from typing import Any, Dict

import pandas as pd
import plotly.express as px
import streamlit as st

from services.api_client import ApiClient, ApiConfig
from components.header import render_header
from components.theme import inject_theme_css


st.set_page_config(page_title="Dashboard - VN-Stock Monitor", layout="wide")
inject_theme_css()

base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
api = ApiClient(ApiConfig(base_url=base_url))

render_header(api)
st.divider()
st.markdown("## Bảng điều khiển")

indices: Dict[str, Any] = {}

def _render_cards(data: Dict[str, Any]) -> None:
    cards = data.get("cards", [])
    cols = st.columns(max(1, len(cards)))
    for i, card in enumerate(cards):
        value = card.get("value", 0)
        delta = card.get("pct_change", 0)
        cols[i].metric(label=card.get("name", "Chỉ số"), value=f"{value:,.2f}", delta=f"{delta:+.2f}%")


try:
    indices = api.market_indices()
    _render_cards(indices)
except Exception as e:
    st.error(f"Không tải được dữ liệu chỉ số: {e}")

st.markdown("### Cổ phiếu biến động mạnh (VN30 proxy)")

g_col, l_col, v_col = st.columns(3)

def _table_for(mover_type: str, container) -> None:
    try:
        res = api.top_movers(mover_type=mover_type, universe="VN30", limit=10)
        df = pd.DataFrame(res.get("items", []))
        container.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        container.error(f"Không tải được dữ liệu top movers: {e}")


_table_for("gainers", g_col)
_table_for("losers", l_col)
_table_for("volume", v_col)

st.markdown("### Đường diễn biến thị trường (theo ngày) — có thể dùng dữ liệu proxy")

try:
    series = indices.get("series", []) if isinstance(indices, dict) else []
    df = pd.DataFrame(series)
    if not df.empty and "time" in df.columns and "close" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        fig = px.line(df.sort_values("time"), x="time", y="close", title="Chuỗi diễn biến thị trường (1D)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Chưa có chuỗi dữ liệu chỉ số từ nguồn hiện tại.")
except Exception as e:
    st.info(f"Không thể lấy chuỗi dữ liệu chỉ số: {e}")

