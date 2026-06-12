IMAGE = butcher-erp
VERSION = $(shell git rev-list --count HEAD)
DOMAIN = erp.snrub.net
ENV_FILE = .env
CONFIG_FILE = docker-compose.yaml

.PHONY: image config deploy setup

image:
	docker buildx build \
		--secret type=file,id=apps_json,src=apps.json \
		--tag $(IMAGE):$(VERSION) \
		--file Containerfile \
		--push .
	sed -i 's/CUSTOM_TAG=.*/CUSTOM_TAG=$(VERSION)/g' $(ENV_FILE)

config:
	docker compose -p $(IMAGE) \
		-f compose.yaml \
		-f overrides/compose.mariadb.yaml \
		-f overrides/compose.redis.yaml \
		-f overrides/compose.noproxy.yaml \
		-f overrides/compose.backup-cron.yaml \
		-f overrides/compose.migrator.yaml \
		--env-file $(ENV_FILE) \
		config > $(CONFIG_FILE)

deploy: image config
	docker compose -p $(IMAGE) \
		-f $(CONFIG_FILE) \
		--pull always \
		up -d 

setup: deploy
	docker compose -p $(IMAGE) exec backend \
		bench new-site $(DOMAIN) \
			--mariadb-user-host-login-scope='%' \
			--db-root-password $(DB_PASSWORD) \
			--admin-password $(ADMIN_PASSWORD) \
			--install-app erpnext \
			--install-app my_app