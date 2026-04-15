.PHONY: up down logs migrate seed api web test install-api install-web setup

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	cd api && alembic upgrade head

seed:
	cd api && py -m app.seed

api:
	cd api && uvicorn app.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	cd api && pytest tests/ -v

install-api:
	cd api && py -m venv venv && venv\Scripts\activate && pip install -r requirements.txt

install-web:
	cd web && npm install

setup: up migrate seed
	@echo "Geo Platform is ready."
	@echo "API: http://localhost:8000/docs"
	@echo "Web: http://localhost:5173"
	@echo "MinIO: http://localhost:9001"
