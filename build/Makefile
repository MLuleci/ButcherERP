IMAGE = butcher-erp
VERSION = $(shell git rev-parse --short HEAD)
ENV_FILE = .env
CONFIG_FILE = docker-compose.yaml

include .env
.PHONY: image config deploy setup

image:
	docker buildx build \
		--secret type=file,id=apps_json,src=apps.json \
		--tag $(IMAGE):$(VERSION) \
		--build-arg CACHE_BUST="$(VERSION)" \
		--file Containerfile .

config: image
	docker compose -p $(IMAGE) \
		-f compose.yaml \
		-f overrides/compose.mariadb.yaml \
		-f overrides/compose.redis.yaml \
		-f overrides/compose.noproxy.yaml \
		-f overrides/compose.backup-cron.yaml \
		-f overrides/compose.migrator.yaml \
		--env-file $(ENV_FILE) \
		config > $(CONFIG_FILE)

deploy: config
	docker compose -p $(IMAGE) -f $(CONFIG_FILE) up -d 

setup: deploy
	docker compose -p $(IMAGE) -f $(CONFIG_FILE) exec backend \
		bench new-site $(DOMAIN) \
			--mariadb-user-host-login-scope='%' \
			--db-root-username root \
			--db-root-password $(DB_PASSWORD) \
			--admin-password $(ADMIN_PASSWORD) \
			--install-app erpnext \
			--install-app my_app
	docker compose -p $(IMAGE) -f $(CONFIG_FILE) exec backend \
		bench --site $(DOMAIN) enable-scheduler