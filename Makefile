up:
	docker compose up -d
down:
	docker compose down
build:
	docker compose build
restart: down build up
logs:
	docker compose logs -f
