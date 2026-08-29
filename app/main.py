"""Utilități Moldova - FastAPI web application."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .auth import ensure_user_created
from .config import APP_NAME, STATIC_DIR
from .db import init_db
from .routers import api, pages
from .services.sync import sync_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_user_created()
    task = asyncio.create_task(sync_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=APP_NAME, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(pages.router)
app.include_router(api.router)
