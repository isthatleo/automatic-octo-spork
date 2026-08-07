#!/usr/bin/env bash
# Starts the local SearXNG instance that SEARXNG_BASE_URL (.env, default
# http://localhost:8888) points at -- providers/web_search/searxng.py is
# already real and wired in; this is just the process it expects to be
# reachable, same "not started by this backend, run it yourself" pattern
# as OmniRoute (see .env.example).
#
# SearXNG itself is a real, separate checkout at ../../../searxng (a
# sibling of nancy-billion, not vendored into this repo -- it's a full
# third-party project with its own history). To set it up from scratch:
#
#   cd ../../..
#   git -c core.protectNTFS=false clone --depth 1 https://github.com/searxng/searxng.git
#   cd searxng
#   python -m venv .venv
#   .venv/Scripts/python.exe -m pip install -r requirements.txt tzdata
#
# Two small, real fixes were needed to run it natively on Windows (no
# Docker/WSL on this machine, and SearXNG only officially supports those
# two) -- both left in place in that checkout, not upstream:
#   1. The repo has systemd-unit-style filenames containing ':' (e.g.
#      "searxng.conf:socket") under utils/templates/ -- invalid on NTFS,
#      hence -c core.protectNTFS=false above just to check the tree out.
#      Irrelevant to running the app itself (those are Linux service unit
#      templates for a production reverse-proxy deployment).
#   2. searx/valkeydb.py unconditionally imported the POSIX-only `pwd`
#      module (used for one diagnostic log line on a failed Valkey/Redis
#      connection -- Valkey is disabled by default config anyway). Patched
#      to guard that import and fall back to a generic log message when
#      `pwd` isn't available.
#   3. searx/settings.yml's search.formats needs `json` added (default is
#      html-only) for providers/web_search/searxng.py's ?format=json calls
#      to work instead of a 403.
#
# `tzdata` is installed because Windows doesn't ship the IANA timezone
# database Python's zoneinfo needs -- without it, a handful of engines
# that do timezone-aware date math (e.g. bilibili) fail to load. Harmless
# either way (SearXNG skips engines that fail to load), just fewer engines.
set -e
cd "$(dirname "$0")/../../../searxng"
export SEARXNG_SETTINGS_PATH="$(pwd)/searx/settings.yml"
export SEARXNG_SECRET="${SEARXNG_SECRET:-$(python -c 'import secrets; print(secrets.token_hex(16))')}"
exec .venv/Scripts/python.exe -m searx.webapp
