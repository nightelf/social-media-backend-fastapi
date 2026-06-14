# social-media-backend-fastapi

FastAPI implementation of the shared social-media API. One of two interchangeable backends — it
satisfies the same [API contract](../social-media-deploy/API_CONTRACT.md) as
`social-media-backend-django`.

> For the full-stack local setup, see the **[deploy repo README](../social-media-deploy/README.md)**.
> This file covers running the FastAPI backend on its own.

## Stack
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async) + asyncpg · Alembic (migrations) · Pydantic v2 (schemas/settings)
- python-jose (JWT) · passlib/pbkdf2_sha256 (password & code hashing) · PostgreSQL

## Layout
```
app/
├── main.py            # app, CORS, exception handlers, /api/health
├── config.py          # pydantic-settings
├── db.py models.py    # async engine/session; SQLAlchemy models
├── schemas.py         # Pydantic request/response models (UTC "Z" datetimes match Django)
├── security.py        # hashing + JWT
├── errors.py          # contract error envelope + handlers
├── services.py        # code issue/verify, masking
├── notifiers.py       # console (default) / smtp / twilio
├── deps.py            # get_current_user, pagination
├── seed.py            # python -m app.seed
└── routers/           # auth.py, users.py, posts.py
alembic/               # migration env + versions
```

## Run standalone (outside Docker)
```bash
cp .env.example .env                 # set DATABASE_URL (asyncpg, db: social_fastapi)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed                   # demo data — login ada / hunter2x!
uvicorn app.main:app --reload --port 8000
```

## Common commands
| Command | Purpose |
|---|---|
| `alembic revision --autogenerate -m "msg"` | Generate a migration after model changes |
| `alembic upgrade head` | Apply migrations |
| `alembic downgrade -1` | Roll back one migration |
| `python -m app.seed` | Seed demo data (idempotent) |

## Endpoints
- API under `/api/` (see the [contract](../social-media-deploy/API_CONTRACT.md))
- Swagger UI: `/docs` · ReDoc: `/redoc` · OpenAPI JSON: `/openapi.json`

## Notes
- `User.is_active` stays `False` until **every** registered contact is verified.
- Verification codes are hashed at rest; plaintext is kept only when `ENV=dev` for the dev-only
  `/api/dev/last-code` endpoint.
- Datetimes serialize as UTC with a trailing `Z` so responses match the Django backend byte-for-byte.
