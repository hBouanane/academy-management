"""FastAPI app factory: migrates + seeds on startup, serves /api and the UI."""

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.sqlite import crud
from app.adapters.sqlite.db import connect, init_db
from app.adapters.sqlite.seed import seed_default_academy
from app.ports.payments import (
    AlreadyPaidError,
    AlreadyReversedError,
    UnknownEnrollmentError,
    UnknownPaymentError,
)
from app.services.payments import (
    AlreadyGuaranteedError,
    ReductionsExceedPriceError,
)

from .routes import router
from .session import Sessions

_ERROR_STATUS: list[tuple[type[Exception], int]] = [
    (UnknownEnrollmentError, 404),
    (UnknownPaymentError, 404),
    (LookupError, 404),
    (AlreadyPaidError, 409),
    (AlreadyReversedError, 409),
    (AlreadyGuaranteedError, 409),
    (ReductionsExceedPriceError, 422),
    (ValueError, 422),  # domain validation (bad bearer, over-100% percent, ...)
    (sqlite3.IntegrityError, 409),
]


def create_app(db_path: str, frontend_dist: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _prepare_database(db_path)
        _file_what_is_missing(db_path)
        yield

    app = FastAPI(title="Academy Management API", lifespan=lifespan)
    app.state.db_path = db_path
    app.state.sessions = Sessions()
    app.middleware("http")(_gate)
    for exception_type, status in _ERROR_STATUS:
        app.add_exception_handler(exception_type, _handler(status))
    app.include_router(router, prefix="/api")
    if frontend_dist and frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


# Deux exceptions, et pas une de plus.
#
# The lock routes: without them, nothing could ever be unlocked. They
# return only the lock state, and write only when the code, the phrase
# or the vendor's answer is right.
#
# Le battement de coeur : la FENÊTRE l'interroge avant de s'ouvrir. Le
# closing it would make the application impossible to launch as soon as
# a code is set -- it would wait twenty seconds, then announce a dead
# server. It says nothing beyond "I answer".
_ALWAYS_OPEN = ("/api/lock", "/api/health")


def _token_of(request: Request) -> str | None:
    """By header for the interface's calls, by cookie for downloads: an
    `<a download>` link cannot carry a header, and a token has no place
    in a URL."""
    return request.headers.get("X-Session-Token") or request.cookies.get(
        "academy_session"
    )


async def _gate(request: Request, call_next):
    """The doorman. While no code is set he lets everything through -- a
    fresh installation has to be usable. Once one exists, nothing is
    written or read without a session token.

    The interface itself (static files) keeps being served: it is what
    displays the unlock screen.
    """
    path = request.url.path
    if not path.startswith("/api") or path.startswith(_ALWAYS_OPEN):
        return await call_next(request)
    connection = connect(request.app.state.db_path)
    try:
        configured = crud.read_lock(connection) is not None
    finally:
        connection.close()
    if configured and not request.app.state.sessions.holds(_token_of(request)):
        return JSONResponse(
            status_code=401, content={"detail": "L'application est verrouillée."}
        )
    return await call_next(request)


def _file_what_is_missing(db_path: str) -> None:
    """Au demarrage, ranger les documents des mois clos qui manquent.

    Un mois vient de se terminer : son export existe sans qu'on ait rien
    demande. Et si l'application n'a pas tourne pendant deux mois, elle
    rattrape le retard en s'ouvrant.

    Jamais au prix du demarrage : si quoi que ce soit resiste, on ouvre
    quand meme."""
    from .routes import reconcile_documents

    connection = connect(db_path)
    try:
        reconcile_documents(connection)
    except Exception:  # noqa: BLE001, S110 - ouvrir prime sur ranger
        pass
    finally:
        connection.close()


def _prepare_database(db_path: str) -> None:
    connection = connect(db_path)
    try:
        init_db(connection)
        seed_default_academy(connection)
    finally:
        connection.close()


def _handler(status: int):
    async def handle(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    return handle
