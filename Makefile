.PHONY: build-WebhookFunction build-AgentRunnerFunction

# Targets que SAM invoca (BuildMethod: makefile en template.yaml).
# Cada Lambda recibe el mismo bundle: src/ como subdirectorio + deps de pip.

define build_lambda
	rm -rf "$(ARTIFACTS_DIR)/src" "$(ARTIFACTS_DIR)"/[A-Za-z]*
	cp -R src "$(ARTIFACTS_DIR)/"
	find "$(ARTIFACTS_DIR)/src" -type d -name '__pycache__' -prune -exec rm -rf {} +
	find "$(ARTIFACTS_DIR)/src" -type d -name '.pytest_cache' -prune -exec rm -rf {} +
	python3 -m pip install \
		--platform manylinux2014_x86_64 \
		--implementation cp \
		--python-version 3.12 \
		--only-binary=:all: \
		--no-compile -q \
		-r src/requirements.txt \
		-t "$(ARTIFACTS_DIR)"
endef

build-WebhookFunction:
	$(build_lambda)

build-AgentRunnerFunction:
	$(build_lambda)
