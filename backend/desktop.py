"""Desktop entry point: boots uvicorn internally, opens a native window.

The client never sees a terminal — this is what the packaged .exe runs.
"""

import socket
import threading
import time
import urllib.request

import uvicorn
import webview

from main import app

HOST = "127.0.0.1"


def pick_free_port() -> int:
    # Ask the OS for a free port so a leftover process or another app
    # on 8000 can never break the client's launch.
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def wait_until_ready(port: int, timeout: float = 15.0) -> bool:
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
    started = time.monotonic()
    port = pick_free_port()

    server = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": HOST, "port": port, "log_level": "warning"},
        daemon=True,  # dies with the window process — no orphan server
    )
    server.start()

    if not wait_until_ready(port):
        raise SystemExit("Backend failed to start")
    print(f"Backend ready in {time.monotonic() - started:.2f}s on port {port}")

    webview.create_window(
        "Academy Management",
        f"http://{HOST}:{port}",
        width=1200,
        height=800,
        min_size=(900, 600),
    )
    webview.start()  # blocks until the window is closed, then the process exits


if __name__ == "__main__":
    main()
