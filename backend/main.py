"""Spike backend: one API route + static serving of the built frontend.

Dev:  uvicorn main:app --reload --port 8000  (frontend runs on the Vite dev server)
Prod: same command, but FastAPI also serves frontend/dist at /
"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Academy Management API")

STUDENTS = [
    {"id": 1, "name": "Yassine El Amrani", "group": "Math A", "monthly_fee": 300, "paid": True},
    {"id": 2, "name": "Salma Bennani", "group": "Physics B", "monthly_fee": 350, "paid": False},
    {"id": 3, "name": "Omar Tazi", "group": "Math A", "monthly_fee": 300, "paid": True},
    {"id": 4, "name": "Nada Alaoui", "group": "English C", "monthly_fee": 250, "paid": False},
    {"id": 5, "name": "Mehdi Berrada", "group": "Physics B", "monthly_fee": 350, "paid": True},
]


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "academy-management"}


@app.get("/api/students")
def list_students():
    return {
        "students": STUDENTS,
        "total": len(STUDENTS),
        "paid": sum(1 for s in STUDENTS if s["paid"]),
        "unpaid": sum(1 for s in STUDENTS if not s["paid"]),
    }


# In production the built frontend is served by this same process.
# Mounted last so /api routes take precedence.
if getattr(sys, "frozen", False):
    # PyInstaller bundle: dist/ is packed next to the code via --add-data
    frontend_dist = Path(sys._MEIPASS) / "frontend" / "dist"
else:
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
