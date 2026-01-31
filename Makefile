.PHONY: help install dev-install clean lint test run run-exe import-data stats
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Guest Database Manager - Available commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	pip install -e .

dev-install: ## Install development dependencies
	pip install -e .
	pip install hatch ruff black mypy pytest

clean: ## Clean up cache and temporary files
	rm -rf __pycache__ src/**/__pycache__ .ruff_cache .mypy_cache .pytest_cache
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

lint: ## Run code quality checks
	ruff check src/ tests/
	ruff format --check src/ tests/

format: ## Format code
	ruff format src/ tests/
	ruff check --fix src/ tests/

test: ## Run tests
	pytest tests/ -v

run-exe: ## Launch using executable file (macOS)
	@echo "🚀 Launching Guest Database Manager executable..."
	@./Guest\ Database\ Manager.command

run: ## Launch the Streamlit application
	python -m guest_database_manager.cli app

import-data: ## Import sample CSV data
	python -m guest_database_manager.cli import "Soulful Guest Questionnaire.csv"

stats: ## Show database statistics
	python -m guest_database_manager.cli stats

build: ## Build the package
	python -m build

# Development shortcuts
dev: dev-install ## Set up development environment

app: run ## Alias for run command
