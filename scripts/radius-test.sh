#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

TEST_RADIUS_USER="${TEST_RADIUS_USER:-teste-prod}"
TEST_RADIUS_PASSWORD="${TEST_RADIUS_PASSWORD:-TesteProd12345}"

echo "Executando radtest local dentro do container FreeRADIUS..."
compose exec -T \
  -e TEST_RADIUS_USER="$TEST_RADIUS_USER" \
  -e TEST_RADIUS_PASSWORD="$TEST_RADIUS_PASSWORD" \
  freeradius sh -lc \
  'radtest "$TEST_RADIUS_USER" "$TEST_RADIUS_PASSWORD" 127.0.0.1:1812 0 "$RADIUS_SECRET" | tee /tmp/radtest.out; grep -q "Access-Accept" /tmp/radtest.out'

echo "RADIUS Access-Accept OK."
