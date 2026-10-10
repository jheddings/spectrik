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
	if [ "$(git symbolic-ref --short -q HEAD)" != "main" ]; then
		echo "ERROR: releases are cut from main"; exit 1
	fi
	# Tag only what origin already has, so a rejected push cannot strand a tag
	# on a commit nobody else can see.
	git fetch --quiet --tags origin
	if [ "$(git rev-parse HEAD)" != "$(git rev-parse '@{u}')" ]; then
		echo "ERROR: main does not match origin/main; pull or push first"; exit 1
	fi
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
	# The module proxy keeps every version it has seen, even after the tag is
	# deleted, so a version it already knows can never be tagged again. Ask
	# for the version list, not the version itself: a lookup of an untagged
	# version is cached as "not found" by the proxy and the checksum database,
	# and the release then cannot be fetched for about ten minutes.
	KNOWN=$(curl -sf "https://proxy.golang.org/{{module}}/@v/list") || {
		echo "ERROR: could not read the version list from the Go module proxy"; exit 1
	}
	if grep -qx "v$VERSION" <<< "$KNOWN"; then
		echo "ERROR: v$VERSION is already on the Go module proxy; versions are immutable"; exit 1
	fi
	git tag -a "v$VERSION" -m "v$VERSION"
	# Push only this tag; `git push --tags` would also publish any stray
	# local tag.
	git push origin "v$VERSION" || {
		git tag -d "v$VERSION"; exit 1
	}

# remove build and test artifacts
clean:
	go clean
	rm -rf tmp

# remove everything including caches
clobber: clean
	lefthook uninstall || true
	go clean -cache -testcache
