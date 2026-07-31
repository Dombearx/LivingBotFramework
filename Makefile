up:
	docker compose up -d
	nohup uv run livingbot-update-server > update-server.log 2>&1 & echo $$! > update-server.pid
down:
	-kill $$(cat update-server.pid) 2>/dev/null
	-rm -f update-server.pid
	docker compose down
build:
	docker compose build
restart: down build up
logs:
	docker compose logs -f
