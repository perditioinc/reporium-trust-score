# Root passthrough to the local OSS dev substrate (see local/).
# $0 / OSS / ADDITIVE / local only. Never touches production cloud.

.PHONY: up down seed smoke logs ps clean local-help

up:
	$(MAKE) -C local up

down:
	$(MAKE) -C local down

seed:
	$(MAKE) -C local seed

smoke:
	$(MAKE) -C local smoke

logs:
	$(MAKE) -C local logs

ps:
	$(MAKE) -C local ps

clean:
	$(MAKE) -C local clean

local-help:
	$(MAKE) -C local help
