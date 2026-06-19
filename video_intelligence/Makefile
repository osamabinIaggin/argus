.PHONY: build up down logs restart shell-api shell-worker clean prune

# Build all images (re-downloads YOLO weights only if layer cache is cold)
build:
	docker compose build

# Start all services in the background
up:
	docker compose up -d

# Stop all services
down:
	docker compose down

# Tail logs from all services (Ctrl-C to stop)
logs:
	docker compose logs -f

# Restart all services
restart:
	docker compose restart

# Open a shell in the running api container
shell-api:
	docker compose exec api bash

# Open a shell in the running worker container
shell-worker:
	docker compose exec worker bash

# Stop services and remove containers + anonymous volumes (keeps named volumes)
clean:
	docker compose down --remove-orphans

# Full reset: remove containers, named volumes (loses all job data + DB), and dangling images
prune:
	docker compose down -v --remove-orphans
	docker image prune -f
