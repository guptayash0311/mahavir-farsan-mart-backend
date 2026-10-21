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

Set `JWT_SECRET` before production. `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` create the first Super Admin when the user table is empty. Reminder jobs run with `python -m app.worker`. File uploads use the local `STORAGE_LOCAL_PATH` directory unless `STORAGE_BACKEND=s3`.

## Sample data

From this directory, with the backend virtualenv active and migrations applied:

```powershell
python -m scripts.seed
```

Set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env` first. The command refuses to run when `APP_ENV` is `production`, and it exits if either bootstrap value is blank. It never prints the Super Admin password. If that email already exists, the password and role are left as they are.

The command then inserts local sample rows for catalog, the homepage, campaigns, carts, wishlists, inquiries, orders, documents, partners, purchases, invoices, and reminders. Inventory is skipped because that application has no tables yet. A second run only checks the Super Admin and does not insert another copy.

Staff and customer sample accounts share the local password `SeedSample#2026`. That is not the Super Admin password. Sign in at `/admin/login` with the bootstrap email and password. Sample customers sign in with `customer01@mahavir.local` through `customer12@mahavir.local`. The staff account is `staff.seed@mahavir.local`. The shop at `/` shows the published homepage, categories, and products.

## Tests

```powershell
pytest
```

If Postgres is down, the suite still runs and skips the live database assertion.
