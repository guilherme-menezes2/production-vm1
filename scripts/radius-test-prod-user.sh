#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

TEST_RADIUS_USER="${TEST_RADIUS_USER:-teste-prod}"
TEST_RADIUS_PASSWORD="${TEST_RADIUS_PASSWORD:-TesteProd12345}"

echo "Criando usuario RADIUS de teste: $TEST_RADIUS_USER"
compose exec -T \
  -e TEST_RADIUS_USER="$TEST_RADIUS_USER" \
  -e TEST_RADIUS_PASSWORD="$TEST_RADIUS_PASSWORD" \
  postgres sh -lc '
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      -c "delete from radreply where username = '\''$TEST_RADIUS_USER'\'';" \
      -c "delete from radcheck where username = '\''$TEST_RADIUS_USER'\'';" \
      -c "insert into radcheck (username, attribute, op, value) values ('\''$TEST_RADIUS_USER'\'', '\''Cleartext-Password'\'', '\'':='\'', '\''$TEST_RADIUS_PASSWORD'\'');" \
      -c "insert into radreply (username, attribute, op, value) values ('\''$TEST_RADIUS_USER'\'', '\''Mikrotik-Rate-Limit'\'', '\'':='\'', '\''10M/5M'\'');"
  '

echo "Usuario RADIUS de teste criado."
