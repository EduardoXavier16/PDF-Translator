from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import jobs, ui


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    app = FastAPI(title="PDF Translator Service")

    base_dir = _get_base_dir()
    templates_dir = base_dir / "templates"
    static_dir = base_dir / "static"

    templates = Jinja2Templates(directory=str(templates_dir))
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(ui.router)
    app.include_router(jobs.router, prefix="/api")

    return app
