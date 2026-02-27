from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import jobs, ui


def create_app() -> FastAPI:
    app = FastAPI(title="PDF Translator Service")

    templates = Jinja2Templates(directory="templates")
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(ui.router)
    app.include_router(jobs.router, prefix="/api")

    return app

