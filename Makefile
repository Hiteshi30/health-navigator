.PHONY: install playground run test

install:
	export PATH="$$HOME/.local/node/bin:$$HOME/.local/bin:$$PATH" && uv sync

playground:
	export PATH="$$HOME/.local/node/bin:$$HOME/.local/bin:$$PATH" && uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	export PATH="$$HOME/.local/node/bin:$$HOME/.local/bin:$$PATH" && uv run python -m app.fast_api_app

test:
	export PATH="$$HOME/.local/node/bin:$$HOME/.local/bin:$$PATH" && uv run pytest
