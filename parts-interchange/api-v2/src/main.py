from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.routers import vehicles, parts, junkyards, feedback, manufacturers
from src.routers.admin import junkyards as admin_junkyards
from src.routers.admin import scrape as admin_scrape
from src.routers.worker import parts as worker_parts
from src.services.iggy import iggy_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await iggy_service.connect()
    except Exception as e:
        print(f"WARNING: Iggy unavailable, scrape triggers disabled: {e}")
    yield
    await iggy_service.disconnect()


app = FastAPI(title="Parts Interchange API", version="2.0.0", lifespan=lifespan)
app.include_router(vehicles.router)
app.include_router(parts.router)
app.include_router(junkyards.router)
app.include_router(feedback.router)
app.include_router(manufacturers.router)
app.include_router(admin_junkyards.router)
app.include_router(admin_scrape.router)
app.include_router(worker_parts.router)
