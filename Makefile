up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f app worker

migrate:
	alembic upgrade head

test:
	ruff check .
	pytest -q

smoke:
	./scripts/smoke.sh
