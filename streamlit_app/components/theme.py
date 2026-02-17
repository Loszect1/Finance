from __future__ import annotations

import streamlit as st


def inject_theme_css() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Spectral:wght@400;600;700&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

:root{
  --bg: #0B0D12;
  --panel: rgba(255,255,255,0.06);
  --panel2: rgba(255,255,255,0.04);
  --line: rgba(255,255,255,0.10);
  --text: rgba(255,255,255,0.92);
  --muted: rgba(255,255,255,0.65);
  --accent: #B8F3C8;
  --danger: #FF6B6B;
  --warn: #F2C94C;
}

html, body, [class*="css"] {
  font-family: "IBM Plex Sans", system-ui, -apple-system, Segoe UI, sans-serif;
}

.stApp {
  background:
    radial-gradient(1200px 600px at 20% 0%, rgba(184,243,200,0.15), transparent 55%),
    radial-gradient(900px 500px at 90% 10%, rgba(242,201,76,0.12), transparent 60%),
    radial-gradient(700px 500px at 70% 80%, rgba(255,107,107,0.10), transparent 60%),
    var(--bg);
  color: var(--text);
}

h1,h2,h3 {
  font-family: "Spectral", serif;
  letter-spacing: 0.2px;
}

.vm-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 14px 14px;
}
.vm-muted { color: var(--muted); }
</style>
        """,
        unsafe_allow_html=True,
    )

