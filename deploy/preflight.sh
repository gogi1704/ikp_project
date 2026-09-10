#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

command -v docker >/dev/null
command -v docker-compose >/dev/null
docker-compose --version >/dev/null

if ss -ltn | awk '{print $4}' | grep -Eq '(^|:)18080$'; then
  echo "STOP: port 18080 is already in use" >&2
  exit 1
fi

test -f .env.production || {
  echo "STOP: create .env.production from .env.production.example" >&2
  exit 1
}

test -d data || {
  echo "STOP: create ./data and grant uid 1000 write access" >&2
  exit 1
}

docker-compose -p cheloveckmed-ikp -f compose.production.yml config >/dev/null
echo "Preflight OK: compose is valid and 127.0.0.1:18080 is free"
