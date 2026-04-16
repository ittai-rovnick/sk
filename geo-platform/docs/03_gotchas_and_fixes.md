# Geo Platform — Gotchas & Fixes

A log of every non-obvious problem hit during the build and how it was fixed.
Anyone setting up this project on a new machine should read this first.

---

## Python version

**Problem:** `python` resolves to Python 2.7 on the dev machine.
**Fix:** Use `py` everywhere. `py` invokes Python 3.13.3 via the Windows Python Launcher.
```powershell
py -m venv venv          # create venv
venv\Scripts\python ...  # once inside venv, python is fine
```

---

## Python 3.13 package compatibility

**Problem:** Several packages in the original requirements don't have Python 3.13 wheels.

| Package | Bad version | Good version | Reason |
|---------|-------------|--------------|--------|
| sqlalchemy | 2.0.30 | 2.0.40 | `__firstlineno__` conflict with py313 |
| pydantic | 2.7.1 | 2.10.6 | pydantic-core 2.18.2 has no py313 wheel |
| pydantic-settings | 2.2.1 | 2.7.1 | pulled in by pydantic |
| psycopg[binary] | 3.1.19 | 3.2.13 | no binary wheel for py313 |

**Fix:** Use the versions in `api/requirements.txt` (already correct).

---

## Windows async event loop (psycopg3)

**Problem:** Windows defaults to `ProactorEventLoop`. psycopg3 async requires `SelectorEventLoop`.
Without the fix, any DB call raises: `psycopg.OperationalError: no running event loop`.

**Fix:** Set the policy BEFORE uvicorn creates its event loop:
```python
# api/run.py — must be first, before importing uvicorn
import asyncio, sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import uvicorn
```
Also set in `api/app/main.py` and `api/alembic/env.py` as belt-and-suspenders.

---

## uvicorn reload=True hides routes on Windows

**Problem:** With `reload=True`, uvicorn spawns a subprocess. On Windows, that subprocess
can pick up stale `.pyc` files and only load routes that existed before the reload.
Result: `/docs` only shows health and auth even though all routers are registered.

**Fix:** `api/run.py` uses `reload=False`. For development, restart the server manually
when code changes.

---

## Alembic — multiple head revisions

**Problem:** Both the meta and features migrations have `down_revision = None`.
Running `alembic upgrade head` fails: "Multiple head revisions are present".

**Fix:** Each migration file has a branch label:
- `api/alembic/versions/001_initial_schema.py` → `branch_labels = ("meta",)`
- `api/alembic/versions/001_features_schema.py` → `branch_labels = ("features",)`

Run as:
```powershell
venv\Scripts\alembic -x db=meta upgrade meta@head
venv\Scripts\alembic -x db=features upgrade features@head
```

---

## Alembic — Windows SelectorEventLoop

**Problem:** Same as above — Alembic's async runner also hits the ProactorEventLoop issue.

**Fix:** In `api/alembic/env.py`, `run_migrations_online()` explicitly creates a SelectorEventLoop on win32:
```python
if sys.platform == "win32":
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_async_migrations())
    loop.close()
else:
    asyncio.run(run_async_migrations())
```

---

## pgbouncer — "no such database: geo_meta"

**Problem:** The bitnami pgbouncer image (`public.ecr.aws/bitnami/pgbouncer:latest`) did not
expose `geo_meta` as a routable database name even though `POSTGRESQL_DATABASE: geo_meta` was set.
Clients connecting with `geo_meta` got: `FATAL: no such database: geo_meta`.

**Fix:** Add explicit env vars to docker-compose.yml pgbouncer service:
```yaml
PGBOUNCER_DATABASE: geo_meta
PGBOUNCER_AUTH_TYPE: md5
```
Already in `docker-compose.yml`.

---

## pydantic-settings — list fields in .env

**Problem:** `api_cors_origins: list[str]` failed to parse from `.env` when written as:
```
API_CORS_ORIGINS=http://localhost:5173
```

**Fix:** List fields must be JSON arrays in `.env`:
```
API_CORS_ORIGINS=["http://localhost:5173"]
```

---

## SQLAlchemy — Mapped[dict] columns need explicit JSONB

**Problem:** `MappedAnnotationError` when using `Mapped[dict]` without specifying the column type.

**Fix:** Always use explicit `JSONB`:
```python
from sqlalchemy.dialects.postgresql import JSONB
properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
```

---

## boto3 blocking async event loop on startup

**Problem:** API hung at "Waiting for application startup." because `boto3` (synchronous) was
called directly in the async lifespan handler.

**Fix:** All boto3 calls wrapped in `asyncio.to_thread()`:
```python
async def ensure_buckets_exist() -> None:
    await asyncio.to_thread(_ensure_buckets_sync)
```

---

## META_DB_URL stuck at port 6432

**Problem:** A system-level `META_DB_URL` environment variable was set on the dev machine
pointing to pgbouncer port 6432. pydantic-settings gives env vars higher priority than `.env`,
so the port 5432 value in `.env` was ignored.

**Fix:** Fixed pgbouncer so port 6432 works correctly (see pgbouncer fix above).
The correct value in `.env` is port 6432 (through pgbouncer).

**Note for PowerShell users:** `set KEY=value` in PowerShell sets a PowerShell variable,
NOT an environment variable. Use `$env:KEY = "value"` instead.

---

## pgbouncer image not on Docker Hub

**Problem:** `bitnami/pgbouncer:latest` was not found on Docker Hub.

**Fix:** Use the AWS ECR mirror: `public.ecr.aws/bitnami/pgbouncer:latest`
Already in `docker-compose.yml`.

---

## MSAL auth removed — replaced with local JWT

**Problem:** MSAL login required real Azure credentials (TENANT_ID, CLIENT_ID, CLIENT_SECRET). Not practical for a dev environment.

**Fix:** Replaced entire auth stack with local HS256 JWT:
- `api/app/auth/local.py` — `create_token()` and `validate_token()`
- `POST /auth/login` — `{username: email}` → `{token, user}`
- `GET /auth/auto-login` — reads OS `%USERNAME%`, auto-creates user in DEV_MODE
- `api/app/dependencies.py` now imports from `auth.local` not `auth.microsoft`
- Migration `004_local_auth.py` makes `ms_object_id` nullable

---

## ms_object_id non-nullable caused 500 on auto-login

**Problem:** Auto-created users have `ms_object_id=None`, but `UserResponse` schema had `ms_object_id: str`. FastAPI returned 500 instead of 200.

**Fix:** Changed to `ms_object_id: str | None` in `api/app/schemas/users.py`.

---

## @mapbox/mapbox-gl-draw draw controls don't work with MapLibre

**Problem:** Draw controls rendered visually but clicking them did nothing. Root cause: `mapbox-gl-draw` has a deep runtime dependency on the real `mapboxgl` library's internal event system. Vite alias `"mapbox-gl": "maplibre-gl"` reroutes module imports but cannot satisfy the internal method calls `mapbox-gl-draw` expects at runtime.

**Fix:** Replaced with `terra-draw`:
```bash
npm remove @mapbox/mapbox-gl-draw
npm install terra-draw
```
`terra-draw` has a first-class `TerraDrawMapLibreGLAdapter`. Modes are React-controlled:
```typescript
const draw = new TerraDraw({
  adapter: new TerraDrawMapLibreGLAdapter({ map }),
  modes: [
    new TerraDrawSelectMode({ flags: { point: { feature: { draggable: true } }, ... } }),
    new TerraDrawPointMode(),
    new TerraDrawLineStringMode(),
    new TerraDrawPolygonMode(),
  ],
});
draw.start();
// activate a mode:
draw.setMode("point");
// get all features:
draw.getSnapshot();
// load features:
draw.addFeatures([...]);
```

---

## Custom groups — groups were MS-only

**Problem:** Original groups model only stored MS Entra groups. No way to create internal groups for users who don't have MS accounts.

**Fix:**
- Added `is_custom: bool` to `ms_groups` table (migration 002)
- Custom groups use `ms_group_id = "custom:{uuid}"` string convention
- `custom_group_members` table stores direct user membership
- `custom_group_ms_links` table links a custom group to real MS Entra group IDs (optional)
- `resolve_custom_group_ids()` in `auth/local.py` merges both sources at login time
- Full CRUD for custom groups in `api/app/routers/groups.py`
