from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import parts, search, vehicles

app = FastAPI(title="Parts Interchange API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(vehicles.router)
app.include_router(parts.router)
app.include_router(search.router)
