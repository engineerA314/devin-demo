.PHONY: up down logs build web controller superset provision-devin provision-devin-environment

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

web:
	cd apps/web && npm run dev

controller:
	cd apps/controller && uvicorn app.main:app --reload --port 8000

superset:
	./scripts/start_local_superset.sh

provision-devin:
	apps/controller/.venv/bin/python scripts/provision_devin.py

provision-devin-environment:
	apps/controller/.venv/bin/python scripts/provision_devin_environment.py
