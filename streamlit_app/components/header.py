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
    left, mid, right = st.columns([2, 5, 2])

    with left:
        st.markdown(f"### {title}")
        st.caption("KBS primary, VCI fallback")

    with mid:
        items = _load_symbols(api.config.base_url)
        options: List[Tuple[str, str]] = []
        for row in items:
            sym = str(row.get("symbol", "")).strip().upper()
            name = str(row.get("organ_name", "") or row.get("company_name", "") or "").strip()
            if not sym:
                continue
            label = f"{sym} — {name}" if name else sym
            options.append((label, sym))

        labels = [x[0] for x in options]
        lookup = {x[0]: x[1] for x in options}

        if labels:
            selected_label = st.selectbox(
                "Search symbol",
                options=labels,
                index=None,
                label_visibility="collapsed",
                placeholder="Type a symbol (e.g., HPG, VNM, FPT)...",
            )
            if selected_label:
                st.session_state["selected_symbol"] = lookup.get(selected_label, "")
        else:
            typed = st.text_input(
                "Search symbol",
                value="",
                label_visibility="collapsed",
                placeholder="Type a symbol (e.g., HPG, VNM, FPT)...",
            )
            st.session_state["selected_symbol"] = typed.strip().upper()

    with right:
        st.caption(f"Backend: {api.config.base_url}")
        if st.button("Refresh data", use_container_width=True):
            _load_symbols.clear()
            st.cache_data.clear()
        if st.button("Open detail", use_container_width=True):
            if st.session_state.get("selected_symbol"):
                st.switch_page("pages/4_Stock_Detail.py")


