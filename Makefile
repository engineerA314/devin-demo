.PHONY: up down logs build doctor web controller superset provision-devin provision-devin-environment

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

doctor:
	docker compose run --rm --build controller python -m app.doctor

web:
	cd apps/web && npm run dev

controller:
	cd apps/controller && uvicorn app.main:app --reload --port 8000

superset:
	./scripts/start_local_superset.sh

provision-devin:
	docker compose run --rm --build -v "$(CURDIR):/workspace" controller \
		python /workspace/scripts/provision_devin.py

provision-devin-environment:
	docker compose run --rm --build -v "$(CURDIR):/workspace" controller \
		python /workspace/scripts/provision_devin_environment.py
