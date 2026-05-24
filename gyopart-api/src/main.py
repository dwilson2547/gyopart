from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.db import create_tables
from src.routers import categories, diagrams, parts, search, vehicles


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(title="Parts Interchange API", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(vehicles.router)
app.include_router(categories.router)
app.include_router(diagrams.router)
app.include_router(parts.router)
app.include_router(search.router)
