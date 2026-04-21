# sk

This repository currently contains the **Geo Platform** project in `geo-platform/`.

## Project structure

- `geo-platform/api` — FastAPI backend
- `geo-platform/web` — React + TypeScript frontend
- `geo-platform/docs` — project documentation and architecture notes
- `geo-platform/docker-compose.yml` — local infrastructure services
- `geo-platform/Makefile` — common project commands

## Quick start

From the project directory:

```bash
cd geo-platform
docker compose up -d
```

Then run the backend and frontend in separate terminals:

```bash
cd geo-platform/api
python run.py
```

```bash
cd geo-platform/web
npm run dev
```

See `geo-platform/COMMANDS.txt` and `geo-platform/docs/` for full setup and operational details.
