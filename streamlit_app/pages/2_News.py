from __future__ import annotations

import os
from typing import List

import pandas as pd
import streamlit as st

from services.api_client import ApiClient, ApiConfig
from components.header import render_header
from components.theme import inject_theme_css


st.set_page_config(page_title="News - VN-Stock Monitor", layout="wide")
inject_theme_css()

base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
api = ApiClient(ApiConfig(base_url=base_url))

render_header(api)
st.divider()
st.markdown("## News Feed")

VN_SOURCES = ["cafef", "tinnhanhchungkhoan", "vnexpress", "vietstock"]
GLOBAL_SOURCES = ["bloomberg"]

left, right = st.columns([3, 2])
with left:
    region = st.selectbox("Region", options=["vn", "global", "all"], index=0)
with right:
    page_size = st.selectbox("Items per load", options=[20, 50, 100], index=1)

if region == "vn":
    available_sources = VN_SOURCES
elif region == "global":
    available_sources = GLOBAL_SOURCES
else:
    available_sources = VN_SOURCES + GLOBAL_SOURCES

sources = st.multiselect("Sources", options=available_sources, default=available_sources)

if "news_limit" not in st.session_state:
    st.session_state.news_limit = page_size

top_bar = st.columns([1, 1, 6])
with top_bar[0]:
    if st.button("Load more"):
        st.session_state.news_limit += page_size
with top_bar[1]:
    if st.button("Reset"):
        st.session_state.news_limit = page_size


def _render_item(item: dict) -> None:
    title = item.get("title", "")
    url = item.get("url", "")
    summary = item.get("summary", "") or item.get("short_description", "")
    source = item.get("source", "unknown")
    publish_time = item.get("publish_time")
    image_url = item.get("image_url")

    with st.container(border=True):
        cols = st.columns([1, 5])
        with cols[0]:
            if image_url:
                st.image(image_url, use_container_width=True)
            else:
                st.caption(source.upper())
        with cols[1]:
            if url:
                st.markdown(f"**[{title}]({url})**")
            else:
                st.markdown(f"**{title}**")
            if summary:
                st.write(summary)
            meta = []
            if publish_time:
                meta.append(str(publish_time))
            meta.append(source)
            st.caption(" | ".join(meta))


try:
    res = api.news_latest(
        limit=int(st.session_state.news_limit),
        region=region if region in ("vn", "global") else "all",
        sources=sources,
    )
    items = res.get("items", [])
    st.caption(f"Loaded {len(items)} items")
    for item in items:
        _render_item(item)
except Exception as e:
    st.error(f"Failed to load news: {e}")

