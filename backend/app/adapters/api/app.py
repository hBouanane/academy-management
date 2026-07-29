"""FastAPI app factory: migrates + seeds on startup, serves /api and the UI."""

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.sqlite.db import connect, init_db
from app.adapters.sqlite.seed import seed_default_academy
from app.ports.payments import (
    AlreadyPaidError,
    AlreadyReversedError,
    UnknownEnrollmentError,
    UnknownPaymentError,
)
from app.services.payments import ReductionsExceedPriceError

from .routes import router

_ERROR_STATUS: list[tuple[type[Exception], int]] = [
    (UnknownEnrollmentError, 404),
    (UnknownPaymentError, 404),
    (LookupError, 404),
    (AlreadyPaidError, 409),
    (AlreadyReversedError, 409),
    (ReductionsExceedPriceError, 422),
    (sqlite3.IntegrityError, 409),
]


def create_app(db_path: str, frontend_dist: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _prepare_database(db_path)
        yield

    app = FastAPI(title="Academy Management API", lifespan=lifespan)
    app.state.db_path = db_path
    for exception_type, status in _ERROR_STATUS:
        app.add_exception_handler(exception_type, _handler(status))
    app.include_router(router, prefix="/api")
    if frontend_dist and frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


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
