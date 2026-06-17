#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

: "${BACKUP_VM2_HOST:?BACKUP_VM2_HOST nao definido}"
: "${BACKUP_VM2_PORT:?BACKUP_VM2_PORT nao definido}"

echo "Verificando conexao TCP com VM2 em ${BACKUP_VM2_HOST}:${BACKUP_VM2_PORT}..."
timeout 5 bash -c "cat < /dev/null > /dev/tcp/${BACKUP_VM2_HOST}/${BACKUP_VM2_PORT}"
echo "Conexao com VM2 OK."
