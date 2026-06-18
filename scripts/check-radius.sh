#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

echo "Verificando processo do FreeRADIUS..."
compose exec -T freeradius sh -lc 'test -s /var/log/radius/radius.log || ps >/dev/null'
echo "FreeRADIUS em execucao."
