.PHONY: up down logs build web controller

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
