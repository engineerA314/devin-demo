.PHONY: up down logs build doctor web controller superset cd1-provision cd1-load-test provision-devin-environment

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

cd1-provision:
	docker exec devin-superset-superset-light-1 \
		/app/.venv/bin/python /app/devin-demo-scripts/setup_cd1_benchmark.py

cd1-load-test:
	.venv/bin/python scripts/run_cd1_load_test.py

provision-devin-environment:
	docker compose run --rm --build -v "$(CURDIR):/workspace" controller \
		python /workspace/scripts/provision_devin_environment.py
