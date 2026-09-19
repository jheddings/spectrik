# justfile for spectrik

module := "github.com/jheddings/spectrik"

# run setup and preflight checks
default: setup preflight

# setup the local development environment
setup:
	go mod tidy
	@command -v lefthook >/dev/null || { echo "lefthook not found: brew install lefthook"; exit 1; }
	lefthook install --force

# auto-format
tidy: setup
	gofmt -w .

# run format and vet checks
check:
	gofmt -l $(git ls-files -co --exclude-standard '*.go') | grep . && exit 1 || true
	go vet ./...

# run unit tests
test:
	go test -race ./...

# full static checks and unit tests
preflight: check test

# verify no uncommitted changes to tracked files
repo-guard:
	test -z "$(git status --porcelain -uno)" || (echo "ERROR: working tree is dirty"; exit 1)

# bump version, tag, and push
release bump="patch": preflight repo-guard
	#!/usr/bin/env bash
	set -euo pipefail
	CURRENT=$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null | sed 's/^v//')
	if [ -z "$CURRENT" ]; then
		CURRENT="0.0.0"
	fi
	IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"
	case "{{bump}}" in
		major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
		minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
		patch) PATCH=$((PATCH + 1)) ;;
		*) echo "Unknown bump type: {{bump}}"; exit 1 ;;
	esac
	VERSION="$MAJOR.$MINOR.$PATCH"
	git tag -a "v$VERSION" -m "v$VERSION"
	git push && git push --tags

# remove build and test artifacts
clean:
	go clean
	rm -rf tmp

# remove everything including caches
clobber: clean
	lefthook uninstall || true
	go clean -cache -testcache
