# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DSI Mapper is a PV (photovoltaic) drone inspection platform. It handles the full pipeline: flight planning, thermal/RGB image processing, AI-based panel detection and defect classification, digital twin asset management, and IEC 62446-3 compliant report generation. Target: SaaS for drone operators inspecting solar farms.

## Architecture

- **Backend**: Python 3.12 + FastAPI (async) at `backend/`
- **Frontend**: React 18 + TypeScript + Vite + Leaflet at `frontend/`
- **Database**: PostgreSQL 16 + PostGIS + GeoAlchemy2 (spatial), Alembic migrations
- **AI**: YOLOv8 (Ultralytics) + PyTorch at `ai/` — panel detection, defect classification, serial OCR
- **DJI Integration**: Thermal SDK wrapper (ctypes) + KMZ generator at `dji/`
- **Processing**: OpenDroneMap via NodeODM (Docker), Celery + Redis task queue
- **Storage**: MinIO (S3-compatible) for images, orthomosaics (COG), reports

## Commands

```bash
# Infrastructure (Docker)
docker compose up -d                          # Start DB, Redis, MinIO, NodeODM

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head                          # Run DB migrations
uvicorn app.main:app --reload --port 8000     # Dev server

# Frontend
cd frontend
npm install
npm run dev                                   # Vite dev server on :5173

# Tests
cd backend && pytest                          # Backend tests
cd backend && pytest tests/test_iec.py -v     # Run specific test file
cd frontend && npm test                       # Frontend tests

# Alembic migrations
cd backend
alembic revision --autogenerate -m "description"  # Generate migration
alembic upgrade head                              # Apply migrations
alembic downgrade -1                              # Rollback one step
```

## Key Conventions

- All spatial data uses **SRID 4326 (WGS84)**. Geometry columns via GeoAlchemy2.
- Database models in `backend/app/models/`, API routes in `backend/app/api/`, business logic in `backend/app/services/`.
- IEC 62446-3 compliance logic (thresholds, classification, validation) lives in `backend/app/iec/`.
- DJI Thermal SDK wrapper at `dji/thermal_sdk/rjpeg_decoder.py` — requires `libdirp.dll` (not in repo, download from DJI).
- KMZ flight plans generated via Jinja2 templates at `dji/kmz_generator/templates/`.
- Heavy processing (ODM, AI inference) runs as Celery async tasks in `backend/app/tasks/`.
- Images stored in MinIO bucket `dsi-mapper`. Orthomosaics as Cloud-Optimized GeoTIFF (COG).
- Defect severity follows IEC 62446-3: Class 1 (dT<10K), Class 2 (10-20K), Class 3 (>=20K).

## DJI Integration

- **Thermal SDK**: `dji/thermal_sdk/` wraps `libdirp` via ctypes. Decodes R-JPEG → numpy float32 temperature matrix.
- **KMZ Generator**: `dji/kmz_generator/` creates DJI Pilot 2 compatible KMZ files with wpml namespace.
- **Simulator**: Requires physical M30T + DJI Assistant 2 Enterprise. See `dji/simulator/README.md`.

## Environment

- GPU: NVIDIA GTX 1080 Ti (11GB VRAM) — ok for inference and small fine-tuning. Heavy training on Vast.ai/RunPod.
- Config via `.env` file (see `.env.example`). Loaded by pydantic-settings in `backend/app/config.py`.
