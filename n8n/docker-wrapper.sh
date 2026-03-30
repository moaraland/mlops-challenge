#!/bin/sh
set -eu

if [ "${1:-}" = "compose" ]; then
  shift

  if command -v docker-compose >/dev/null 2>&1; then
    exec docker-compose "$@"
  fi
fi

exec /usr/bin/docker-real "$@"
