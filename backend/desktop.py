"""Desktop entry point — what the packaged AcademyManagement.exe runs.

Boots uvicorn internally on a free 127.0.0.1 port, opens a native window,
and backs up the database when the window closes. The client never sees a
terminal.
"""

import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import uvicorn
import webview

from app.adapters.api.app import create_app

HOST = "127.0.0.1"
BACKUPS_TO_KEEP = 30


def data_dir() -> Path:
    """%APPDATA%\\AcademyManagement (override with ACADEMY_DATA_DIR)."""
    override = os.environ.get("ACADEMY_DATA_DIR")
    if override:
        base = Path(override)
    else:
        appdata = os.environ.get("APPDATA") or str(Path.home())
        base = Path(appdata) / "AcademyManagement"
    base.mkdir(parents=True, exist_ok=True)
    return base


def frontend_dist() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "frontend" / "dist"
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


def backup_database(db_path: Path, stamp: str | None = None) -> Path | None:
    """Copy data.db into backups/ next to it; keep only the newest N."""
    if not db_path.exists():
        return None
    backups = db_path.parent / "backups"
    backups.mkdir(exist_ok=True)
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005 - local wall-clock names are what the client expects
    target = backups / f"data-{stamp}.db"
    shutil.copy2(db_path, target)
    _prune(backups)
    return target


def _prune(backups: Path, keep: int = BACKUPS_TO_KEEP) -> None:
    files = sorted(backups.glob("data-*.db"))
    for old in files[:-keep]:
        old.unlink()


def pick_free_port() -> int:
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def wait_until_ready(port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    url = f"http://{HOST}:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def main() -> None:
    db_path = data_dir() / "data.db"
    app = create_app(str(db_path), frontend_dist=frontend_dist())
    port = pick_free_port()
    threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": HOST, "port": port, "log_level": "warning"},
        daemon=True,  # dies with the window - no orphan server
    ).start()
    if not wait_until_ready(port):
        raise SystemExit("Backend failed to start")
    webview.create_window(
        "Academy Management",
        f"http://{HOST}:{port}",
        width=1280,
        height=850,
        min_size=(1000, 650),
    )
    webview.start()  # blocks until the window closes
    backup_database(db_path)


if __name__ == "__main__":
    main()
