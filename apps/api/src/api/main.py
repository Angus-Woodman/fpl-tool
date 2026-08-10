from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.logging import configure_logging
from api.routers.fixtures import router as fixtures_router
from api.routers.health import router as health_router
from api.routers.imports import router as imports_router
from api.routers.players import router as players_router

configure_logging()

app = FastAPI(title="FPL Tool API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(imports_router)
app.include_router(players_router)
app.include_router(fixtures_router)
