.PHONY: up down logs migrate seed api web test install-api install-web setup

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	cd api && venv/Scripts/alembic -x db=meta upgrade meta@head
	cd api && venv/Scripts/alembic -x db=features upgrade features@head

seed:
	cd api && py -m app.seed

api:
	cd api && venv/Scripts/py run.py

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
