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
# Les routes du verrou : sans elles, on ne pourrait jamais déverrouiller.
# Elles ne rendent que l'état du verrou et n'écrivent que si le code, la
# phrase ou la réponse de l'éditeur sont justes.
#
# Le battement de coeur : la FENÊTRE l'interroge avant de s'ouvrir. Le
# fermer rendrait l'application impossible à lancer dès qu'un code est
# posé — elle attendrait vingt secondes puis annoncerait un serveur
# mort. Il ne dit rien d'autre que « je réponds ».
_ALWAYS_OPEN = ("/api/lock", "/api/health")


def _token_of(request: Request) -> str | None:
    """Par en-tête pour les appels de l'interface, par cookie pour les
    téléchargements : un lien `<a download>` ne peut porter aucun
    en-tête, et on ne met pas un jeton dans une adresse."""
    return request.headers.get("X-Session-Token") or request.cookies.get(
        "academy_session"
    )


async def _gate(request: Request, call_next):
    """Le portier. Tant qu'aucun code n'est posé, il laisse tout passer —
    une installation neuve doit pouvoir servir. Dès qu'il y en a un,
    plus rien ne s'écrit ni ne se lit sans un jeton de session.

    L'interface elle-même (fichiers statiques) reste servie : c'est elle
    qui affiche l'écran de déverrouillage.
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
