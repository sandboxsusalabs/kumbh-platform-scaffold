.PHONY: install run dev test seed migrate lint up down clean

install:            ## install API + test dependencies
	pip install -r requirements.txt

run:                ## run the API (reads .env)
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:                ## run with reload
	cd backend && uvicorn app.main:app --reload --port 8000

test:               ## run the API test suite
	cd backend && python -m pytest -q

seed:               ## load demo facilities, ghats, zones, snan schedule
	cd backend && python -m app.seeds.seed

migrate:            ## apply migrations (production path)
	cd backend && alembic upgrade head

revision:
	cd backend && alembic revision --autogenerate -m "$(m)"

up:                 ## full local stack
	docker compose up --build

down:
	docker compose down

clean:
	rm -f backend/kumbh_dev.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
