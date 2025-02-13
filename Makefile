.PHONY: format
format:
	uvx ruff check --select I --fix
	uvx ruff format


.PHONY: run
run:
	uv run run.py