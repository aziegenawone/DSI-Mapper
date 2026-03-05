from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import flights, ingestion, sites, inspections, reports, serials


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="DSI Mapper",
    description="PV drone inspection platform — flight planning, AI analysis, digital twin, IEC 62446-3 reports",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sites.router, prefix="/api/sites", tags=["sites"])
app.include_router(flights.router, prefix="/api/flights", tags=["flights"])
app.include_router(ingestion.router, prefix="/api/ingestion", tags=["ingestion"])
app.include_router(inspections.router, prefix="/api/inspections", tags=["inspections"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(serials.router, prefix="/api/serials", tags=["serials"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
