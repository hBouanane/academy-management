"""Dev server: the API alone on 127.0.0.1:8000 — Vite proxies /api here.

The desktop build (desktop.py) is the real entry point; this one exists so
the frontend can be developed against a scratch database, no window involved.
"""

from pathlib import Path

import uvicorn

from app.adapters.api.app import create_app

app = create_app(str(Path(__file__).parent / "dev.db"))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
