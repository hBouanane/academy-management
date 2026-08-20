"""Desktop entry point — what the packaged AcademyManagement.exe runs.

Boots uvicorn internally on a free 127.0.0.1 port, opens a native window,
and backs up the database when the window closes. The client never sees a
terminal.
"""

import ctypes
import os
import socket
import sqlite3
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
    """Snapshot data.db into backups/ next to it; keep only the newest N.

    Uses SQLite's online backup API, never a raw file copy: it takes proper
    locks, so the snapshot is consistent even if the server thread is
    mid-write, and a hot journal is rolled back rather than discarded.
    """
    if not db_path.exists():
        return None
    backups = db_path.parent / "backups"
    backups.mkdir(exist_ok=True)
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005 - local wall-clock names are what the client expects
    target = backups / f"data-{stamp}.db"
    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    if _same_as_last(target, backups):
        # Rien n a bouge depuis la derniere fois : ouvrir l application
        # pour consulter un chiffre ne merite pas une photographie.
        # Trente copies identiques chasseraient les vraies.
        target.unlink()
        return None
    _prune(backups)
    return target


def _same_as_last(fresh: Path, backups: Path) -> bool:
    """Cette photographie dit-elle exactement la meme chose que la
    precedente ?

    On compare le contenu, pas la date : deux fermetures dans la meme
    seconde ont la meme heure, et une base qui n a pas bouge a la meme
    taille. Seul le contenu tranche.
    """
    others = sorted(
        item for item in backups.glob("data-*.db") if item.name != fresh.name
    )
    if not others:
        return False
    try:
        return _fingerprint(fresh) == _fingerprint(others[-1])
    except OSError:
        # Dans le doute on garde : une copie de trop ne coute rien, une
        # copie manquante coute tout.
        return False


def _fingerprint(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _prune(backups: Path, keep: int = BACKUPS_TO_KEEP) -> None:
    """Une photographie par fermeture remplirait le disque en quelques
    annees : on garde les plus recentes, soit environ un mois."""
    files = sorted(backups.glob("data-*.db"))
    for stale in files[:-keep]:
        stale.unlink()


def _schema(db_path: Path) -> int:
    """La version du schéma, telle que SQLite la porte dans le fichier."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def database_complaint(db_path: Path) -> str | None:
    """Ce qui empêche d'ouvrir cette base, dit en clair — ou rien.

    Une sauvegarde ANCIENNE se rattrape toute seule : les migrations la
    ramènent au présent au démarrage. C'est l'inverse qui est dangereux —
    un fichier écrit par une version plus récente contient des colonnes
    que cette version-ci ne connaît pas.

    Sans ce garde-fou, le client lirait « le serveur interne n'a pas
    démarré » et n'aurait aucune idée de la vraie raison.
    """
    if not db_path.exists():
        return None
    from app.adapters.sqlite.migrations import latest_version

    found = _schema(db_path)
    known = latest_version()
    if found <= known:
        return None
    return (
        "Cette sauvegarde vient d'une version plus récente de"
        f" l'application (schéma {found}, celle-ci connaît {known}).\n\n"
        "Installez la dernière version, ou restaurez une sauvegarde plus"
        " ancienne."
    )


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


_ERROR_ALREADY_EXISTS = 183
_kernel32 = (
    ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None
)
_mutex_handle = None  # keeps the mutex alive for the process lifetime


def another_instance_is_running() -> bool:
    """Named-mutex guard: two windows over one ledger invite double entry.

    use_last_error is essential - plain windll.GetLastError() reads a stale
    value and the guard silently never fires.
    """
    global _mutex_handle
    if _kernel32 is None:
        return False
    _mutex_handle = _kernel32.CreateMutexW(None, False, "AcademyManagementSingleton")
    return ctypes.get_last_error() == _ERROR_ALREADY_EXISTS


def _fatal(message: str) -> None:
    """--noconsole means stderr goes nowhere; the client needs a real dialog."""
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "Academy Management", 0x10)
    raise SystemExit(message)


def main() -> None:
    if another_instance_is_running():
        _fatal("L'application est déjà ouverte.")
    db_path = data_dir() / "data.db"
    complaint = database_complaint(db_path)
    if complaint:
        _fatal(complaint)
    app = create_app(str(db_path), frontend_dist=frontend_dist())
    port = pick_free_port()
    threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": HOST, "port": port, "log_level": "warning"},
        daemon=True,  # dies with the window - no orphan server
    ).start()
    if not wait_until_ready(port):
        _fatal("Le serveur interne n'a pas démarré. Contactez le support.")
    # pywebview blocks downloads unless told otherwise — without this, the
    # Excel export button silently does nothing in the packaged app.
    webview.settings["ALLOW_DOWNLOADS"] = True
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
