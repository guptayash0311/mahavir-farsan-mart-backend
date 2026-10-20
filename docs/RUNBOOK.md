# Runbook

## Deploy

1. Set production secrets outside git: `DATABASE_URL`, `JWT_SECRET` (at least 32 characters), `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`, `CORS_ORIGINS`, object-storage credentials, and `REDIS_URL`.
2. Build the API image from `codebase/backend` and the web image from `codebase/frontend`.
3. Start PostgreSQL, MinIO, and Redis first. Apply migrations with `alembic upgrade head` before the API serves traffic. The API image does this on startup.
4. Put HTTPS in front of both apps. Restrict CORS to the public origin.
5. Sign in once with the bootstrap Super Admin, then remove `BOOTSTRAP_ADMIN_PASSWORD` from the environment. The bootstrap runs only while the user table is empty.

## Migrate

```powershell
alembic upgrade head
```

Run this against the target database before switching traffic.

## Restore

```powershell
python -m scripts.backup backup backups/mahavir.dump
python -m scripts.backup restore backups/mahavir.dump
```

`pg_dump` and `pg_restore` must be on PATH. Restore into a database you can afford to replace. Confirm `GET /api/v1/health` reports `database: ok`, then sign in and open a known product.

## Rotate the JWT secret

1. Set a new `JWT_SECRET`.
2. Restart the API. Existing access and refresh tokens stop working.
3. Staff and customers sign in again.
