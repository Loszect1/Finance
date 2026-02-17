from __future__ import annotations

import os

import streamlit as st

from services.api_client import ApiClient, ApiConfig
from components.theme import inject_theme_css


def main() -> None:
    st.set_page_config(
        page_title="VN-Stock Monitor - Giám sát thị trường chứng khoán Việt Nam",
        page_icon="",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme_css()

    base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
    api = ApiClient(ApiConfig(base_url=base_url))

    # Sidebar
    with st.sidebar:
        st.markdown("## VN-Stock Monitor")
        st.caption("FastAPI + vnstock + Streamlit (giám sát thị trường chứng khoán Việt Nam)")
        st.text_input("Địa chỉ Backend", value=base_url, key="backend_url", disabled=True)
        if st.button("Kiểm tra trạng thái"):
            try:
                data = api.health()
                st.success(data.get("status", "ok") or "ok")
            except Exception as e:
                st.error(str(e))

    st.markdown("## Chào mừng")
    st.markdown(
        '<div class="vm-panel"><div class="vm-muted">Sử dụng các trang trong thanh bên trái để điều hướng: Dashboard, News, Market, Stock Detail.</div></div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

