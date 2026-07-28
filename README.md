# Academy Management

Desktop app for managing an academy (students, payments, exports), built as an offline-first Windows application.

## Stack

- **Frontend:** React + Vite + Tailwind CSS + shadcn/ui
- **Backend:** FastAPI + SQLite (`sqlite3`), serving the built frontend as static files
- **Excel export:** openpyxl
- **Desktop shell:** pywebview
- **Packaging:** PyInstaller (`--onedir`) + Inno Setup → Windows installer

## Architecture

In production, a single Python process runs uvicorn on `127.0.0.1`, serves the API under `/api` and the built React app as static files, and opens a native window via pywebview. No Node, no CORS, fully offline on the client machine.

In development, the Vite dev server proxies `/api` to FastAPI for hot reload.
