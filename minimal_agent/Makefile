.PHONY: format lint lint-fix

# Format code using Ruff
format:
	uv run ruff format .

# Lint code using Ruff
lint:
	uv run ruff check .

# Automatically fix linting issues using Ruff
lint-fix:
	uv run ruff check --fix .
