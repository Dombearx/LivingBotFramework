# make runs recipes through a non-interactive shell, which doesn't source
# .bashrc/.profile, so uv's install directory has to be added explicitly here
# even though it's already on PATH in an interactive shell.
export PATH := $(HOME)/.local/bin:$(HOME)/.cargo/bin:$(PATH)

up:
	docker compose up -d
	@if [ -f update-server.pid ] && kill -0 $$(cat update-server.pid) 2>/dev/null; then \
		echo "update-server already running"; \
	else \
		nohup uv run update_server.py > update-server.log 2>&1 & echo $$! > update-server.pid; \
		echo "Waiting for update-server to start..."; \
		for i in $$(seq 1 30); do \
			curl -sf http://localhost:40000/health > /dev/null 2>&1 && exit 0; \
			sleep 1; \
		done; \
		echo "update-server did not become ready in time, tail of update-server.log:"; \
		tail -n 50 update-server.log; \
		exit 1; \
	fi
down:
	-kill $$(cat update-server.pid) 2>/dev/null
	-rm -f update-server.pid
	docker compose down
build:
	docker compose build
restart: down build up
logs:
	docker compose logs -f
