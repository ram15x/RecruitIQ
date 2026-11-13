"""Runs the API inside the dashboard's own process, for hosts that run only one program (Streamlit Community Cloud).
Turn it on with RECRUITIQ_EMBED=1. The candidate interview page is then not reachable from outside, so use it for demos."""
import os
import secrets
import tempfile
import threading
import time

import httpx
import streamlit as st


@st.cache_resource
def start_api(port: int = 8000) -> str:
    tmp = tempfile.gettempdir()
    for k, v in {
        "RECRUITIQ_DB_URL": f"sqlite:///{tmp}/recruitiq.db",
        "RECRUITIQ_MEDIA_DIR": f"{tmp}/recruitiq-media",
        "RECRUITIQ_JWT_SECRET": secrets.token_hex(32),
        "RECRUITIQ_DEMO": "1",
        "RECRUITIQ_BOOTSTRAP_USER": "demo",
        "RECRUITIQ_BOOTSTRAP_PASSWORD": "recruiter-demo-2026",
        "RECRUITIQ_RETENTION_DAYS": "7",
        "RECRUITIQ_API_URL": f"http://127.0.0.1:{port}",
        "RECRUITIQ_DEMO_HINT": "Demo login: username demo, password recruiter-demo-2026",
    }.items():
        os.environ.setdefault(k, v)
    import uvicorn

    from recruitiq.api.app import app_factory
    server = uvicorn.Server(uvicorn.Config(app_factory, factory=True, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                return url
        except httpx.HTTPError:
            time.sleep(0.5)
    raise RuntimeError("the embedded API did not start")
