from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.clustering import router as clustering_router
from app.api.data_center import router as data_center_router
from app.api.discovery import router as discovery_router
from app.api.graphs import router as graphs_router
from app.api.health import router as health_router
from app.api.job_parsing import router as job_parsing_router
from app.api.jobs import router as jobs_router
from app.api.taxonomy import router as taxonomy_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.log_level)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(taxonomy_router, prefix=settings.api_prefix)
app.include_router(jobs_router, prefix=settings.api_prefix)
app.include_router(job_parsing_router, prefix=settings.api_prefix)
app.include_router(data_center_router, prefix=settings.api_prefix)
app.include_router(clustering_router, prefix=settings.api_prefix)
app.include_router(discovery_router, prefix=settings.api_prefix)
app.include_router(graphs_router, prefix=settings.api_prefix)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
