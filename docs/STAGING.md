# Staging

Staging uses the same Compose services as production, with its own database, bucket, and secrets.

From `codebase/`:

```powershell
docker compose -f docker-compose.yml -f docker-compose.staging.yml up --build
```

Set `JWT_SECRET`, `BOOTSTRAP_ADMIN_EMAIL`, and `BOOTSTRAP_ADMIN_PASSWORD` in the shell before starting. Do not commit them.

Before calling a feature done, repeat the affected flow on this stack: sign in, change the record, and confirm the public site shows only published data.
