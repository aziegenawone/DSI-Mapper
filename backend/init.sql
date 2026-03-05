-- Enable PostGIS and TimescaleDB extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
-- TimescaleDB requires the timescaledb image; skip if not available
-- CREATE EXTENSION IF NOT EXISTS timescaledb;
