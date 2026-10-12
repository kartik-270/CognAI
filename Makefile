.PHONY: up down build logs tf-init tf-plan tf-apply clean

# Docker Compose commands
up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f

clean:
	docker-compose down -v --remove-orphans

# Database commands
db-migrate:
	docker-compose exec backend alembic revision --autogenerate -m "$(m)"

db-upgrade:
	docker-compose exec backend alembic upgrade head

# Terraform commands
tf-init:
	cd terraform && terraform init

tf-plan:
	cd terraform && terraform plan

tf-apply:
	cd terraform && terraform apply -auto-approve

# Backend development commands
lint:
	cd backend && flake8 app
	cd backend && black --check app

format:
	cd backend && black app
