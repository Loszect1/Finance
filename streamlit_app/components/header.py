from __future__ import annotations

from typing import Any, Dict, List, Tuple

import streamlit as st

from services.api_client import ApiClient, ApiConfig


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def _load_symbols(api_base_url: str) -> List[Dict[str, Any]]:
    api = ApiClient(ApiConfig(base_url=api_base_url))
    data = api.stocks_list()
    return data.get("items", [])


def render_header(api: ApiClient, title: str = "VN-Stock Monitor") -> None:
    # Simplified layout: remove search bar column, keep title + action buttons
    left, right = st.columns([3, 2])

    with left:
        st.markdown(f"### {title}")
        st.caption("KBS primary, VCI fallback")

    with right:
        st.caption(f"Backend: {api.config.base_url}")
        if st.button("Refresh data", use_container_width=True):
            _load_symbols.clear()
            st.cache_data.clear()
        if st.button("Open detail", use_container_width=True):
            if st.session_state.get("selected_symbol"):
                st.switch_page("pages/4_Stock_Detail.py")


