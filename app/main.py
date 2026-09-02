"""Utilități Moldova - FastAPI web application."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import ensure_user_created
from .config import APP_NAME, STATIC_DIR
from .db import init_db
from .routers import api, pages
from .services.sync import invoice_job_worker, sync_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_user_created()
    task = asyncio.create_task(sync_loop())
    job_worker = asyncio.create_task(invoice_job_worker())
    try:
        yield
    finally:
        task.cancel()
        job_worker.cancel()
        for t in (task, job_worker):
            try:
                await t
            except asyncio.CancelledError:
                pass


app = FastAPI(title=APP_NAME, lifespan=lifespan)

# CORS: allow the mobile (Expo/React Native) app and any frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(pages.router)
app.include_router(api.router)
