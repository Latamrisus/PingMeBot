build:
	docker compose down
	docker compose up --build
up:
	docker compose up

down:
	docker compose down

restart:
	docker compose restart

volumes:
	docker compose down -v

ro:
	docker compose down --remove-orphans

vro:
	docker compose down -v --remove-orphans

prune:
	docker system prune -f