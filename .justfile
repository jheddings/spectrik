# justfile for spectrik

basedir := justfile_directory()
srcdir := basedir / "src"

appname := "spectrik"
appver := `uv version --short`

# run setup and preflight checks
default: setup preflight

# setup the local development environment
setup: venv
    uv run pre-commit install --install-hooks --overwrite

# sync the virtual environment
venv:
    uv sync --all-extras

# auto-format, lint-fix, and type-check
tidy: setup
    uv run ruff format "{{srcdir}}" "{{basedir}}/tests"
    uv run ruff check --fix "{{srcdir}}" "{{basedir}}/tests"
    uv run pyright "{{srcdir}}" "{{basedir}}/tests"

# run unit tests
test: setup
    uv run pytest "{{basedir}}/tests"

# run pre-commit hooks on all files
precommit: setup
    uv run pre-commit run --all-files --verbose

# full pre-commit + unit tests (gate for commits)
preflight: precommit test

# build distribution packages
build: preflight
    uv build

# bump version, commit, tag, and push
release bump="patch": preflight
    #!/usr/bin/env bash
    uv version --bump {{bump}}
    VERSION=$(uv version --short)
    git add pyproject.toml uv.lock
    git commit -m "bump version to $VERSION"
    git tag -a "v$VERSION" -m "v$VERSION"
    git push && git push --tags

# remove caches and compiled files
clean:
    rm -f "{{basedir}}/.coverage"
    rm -rf "{{basedir}}/.pytest_cache"
    rm -rf "{{basedir}}/.ruff_cache"
    find "{{basedir}}" -name "*.pyc" -delete
    find "{{basedir}}" -name "__pycache__" -type d -exec rm -rf {} +

# remove everything including venv and dist
clobber: clean
    uv run pre-commit uninstall || true
    rm -rf "{{basedir}}/dist"
    rm -rf "{{basedir}}/.venv"
    find "{{basedir}}" -name "*.log" -delete
