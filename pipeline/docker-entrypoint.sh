#!/bin/sh
set -eu

DB_PATH="${KNOWN_LOG_DB_PATH:-/data/known_patterns.db}"
DB_DIR="$(dirname "$DB_PATH")"

mkdir -p "$DB_DIR"
touch "$DB_PATH"
chown -R snooplog:snooplog "$DB_DIR"

exec gosu snooplog "$@"
