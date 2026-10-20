# Mahavir Farsan Mart API

FastAPI service for Mahavir Farsan Mart. This project is its own repository. The React app lives in a separate repository and calls this API at `http://localhost:8000`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```

`requirements.txt` is the runtime install. `requirements-dev.txt` includes it plus Pytest. Use the dev file in the virtualenv.

`.env` is loaded from this directory. Leave `DATABASE_URL` blank to build it from the `POSTGRES_*` values. The password is URL-encoded, so a character such as `@` stays part of the password. Set `DATABASE_URL` only when you already have a fully encoded URL.

## Run

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Health check: http://localhost:8000/api/v1/health

## Tests

```powershell
pytest
```

If Postgres is down, the suite still runs and skips the live database assertion.
