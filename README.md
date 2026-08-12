# Metadata-driven ETL backend

FastAPI foundation for a metadata-driven ETL platform.

## Local setup

1. Copy `.env.example` to `.env` and fill in integration credentials as needed.
2. Install dependencies: `pip install -e ".[dev]"`.
3. Apply migrations: `alembic upgrade head`.
4. Start the API: `uvicorn app.main:app --reload`.

The default local configuration uses SQLite. The example environment and Docker
Compose configuration use PostgreSQL for the metadata database.

## Endpoints

- `GET /api/v1/health` checks whether the API process is alive.
- `GET /api/v1/health/ready` checks metadata database connectivity.
- `GET /docs` exposes Swagger UI outside production.

Each response includes `X-Request-ID` and `X-Process-Time-Ms` headers. Errors use
a consistent JSON envelope containing an error code, message, and request ID.

## Configuration

Configuration is loaded from environment variables and an optional `.env` file.
See `.env.example` for application, CORS, metadata database, Azure, Databricks,
Airflow, and storage settings. Secrets are never hard-coded in the application.
