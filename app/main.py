"""Utilități Moldova - FastAPI web application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .auth import ensure_user_created
from .config import APP_NAME, STATIC_DIR
from .db import init_db
from .routers import api, pages


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_user_created()
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(pages.router)
app.include_router(api.router)
