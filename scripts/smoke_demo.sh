#!/usr/bin/env bash
# Smoke e2e de la demo (ejecutar tras `docker compose up -d` y esperar a que arranque).
set -euo pipefail

API="${API:-http://localhost:8080}"
AUTH="${AUTH:-http://localhost:8000}"
ANON="${ANON:?exporta ANON con la anon key de .env.docker}"
EMAIL="${DEMO_EMAIL:-demo@mnemo.local}"
PASS="${DEMO_PASSWORD:-mnemo-demo-1234}"

echo "1) health del backend"
curl -fsS "$API/v2/health" >/dev/null && echo "  ok"

echo "2) login del usuario demo"
TOKEN=$(curl -fsS "$AUTH/auth/v1/token?grant_type=password" \
  -H "apikey: $ANON" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
[ -n "$TOKEN" ] && echo "  token obtenido"

echo "3) endpoint autenticado /v2/orgs"
curl -fsS "$API/v2/orgs" -H "Authorization: Bearer $TOKEN" >/dev/null && echo "  ok (auth válida)"

echo "SMOKE OK"
