from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.api_client import ApiClient, ApiConfig
from components.header import render_header
from components.theme import inject_theme_css


st.set_page_config(page_title="Stock Detail - VN-Stock Monitor", layout="wide")
inject_theme_css()

base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
api = ApiClient(ApiConfig(base_url=base_url))

render_header(api)
st.divider()
st.markdown("## Chi tiết cổ phiếu")

top = st.columns([2, 2, 2, 6])
with top[0]:
    symbol = st.text_input(
        "Mã cổ phiếu",
        value="",
        placeholder="Nhập mã, ví dụ: VCB, FPT, HPG",
    ).strip().upper()
with top[1]:
    interval = st.selectbox("Khung thời gian", options=["1D", "1H", "15m", "5m"], index=0)
with top[2]:
    length = st.selectbox("Độ dài dữ liệu", options=["1M", "3M", "6M", "1Y", "100b"], index=0)

if not symbol:
    st.stop()

q_col, p_col = st.columns([2, 3])

with q_col:
    st.markdown("### Giá và thông tin giao dịch")
    try:
        q = api.stock_quote(symbol)
        st.json(q)
    except Exception as e:
        st.error(str(e))

with p_col:
    st.markdown("### Biểu đồ giá (nến)")
    try:
        hist = api.stock_history(symbol, interval=interval, length=length)
        df = pd.DataFrame(hist.get("items", []))
        if not df.empty and {"time", "open", "high", "low", "close"}.issubset(df.columns):
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time")
            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=df["time"],
                        open=df["open"],
                        high=df["high"],
                        low=df["low"],
                        close=df["close"],
                    )
                ]
            )
            fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Chưa có đủ dữ liệu OHLCV để vẽ biểu đồ nến.")
    except Exception as e:
        st.error(str(e))

st.markdown("### Doanh nghiệp & chỉ số cơ bản")
left, right = st.columns(2)
with left:
    st.markdown("#### Thông tin doanh nghiệp")
    try:
        profile = api.stock_profile(symbol)
        st.json(profile)
    except Exception as e:
        st.error(str(e))
with right:
    st.markdown("#### Các chỉ số tài chính (năm)")
    try:
        ratios = api.stock_ratios(symbol, period="year")
        df = pd.DataFrame(ratios.get("items", []))
        st.dataframe(df.tail(10), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(str(e))

st.markdown("### Tin tức mới nhất về doanh nghiệp")
try:
    news = api.stock_news(symbol, limit=20)
    items = news.get("items", [])
    for item in items:
        title = item.get("head") or item.get("news_title") or item.get("title") or ""
        url = item.get("url") or item.get("link") or ""
        publish_time = item.get("publish_time") or item.get("public_date") or ""
        if url:
            st.markdown(f"- [{title}]({url}) ({publish_time})")
        else:
            st.markdown(f"- {title} ({publish_time})")
except Exception as e:
    st.error(str(e))

