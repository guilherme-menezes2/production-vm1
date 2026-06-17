#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

MIGRATIONS_DIR="${MIGRATIONS_DIR:-$ROOT_DIR/postgres/migrations}"
if [ ! -d "$MIGRATIONS_DIR" ]; then
  MIGRATIONS_DIR="$ROOT_DIR/../postgres/migrations"
fi

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "Diretorio de migrations nao encontrado." >&2
  exit 1
fi

echo "Aplicando migrations em $POSTGRES_DB..."
find "$MIGRATIONS_DIR" -maxdepth 1 -type f -name '*.sql' | sort | while IFS= read -r migration; do
  echo "Aplicando $(basename "$migration")"
  compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$migration"
done
echo "Migrations aplicadas."
