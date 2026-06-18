#!/usr/bin/env sh
set -eu

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY nao definido}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD nao definido}"
: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:?POSTGRES_DB nao definido}"
: "${POSTGRES_USER:?POSTGRES_USER nao definido}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD nao definido}"
: "${RESTIC_KEEP_DAILY:=7}"
: "${RESTIC_KEEP_WEEKLY:=4}"
: "${RESTIC_KEEP_MONTHLY:=12}"

export PGPASSWORD="$POSTGRES_PASSWORD"

timestamp="$(date '+%Y%m%d-%H%M%S')"
workdir="/backups/current"
dumpdir="$workdir/postgres"
manifest="$workdir/manifest.txt"

mkdir -p "$dumpdir"
find "$workdir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
mkdir -p "$dumpdir"

echo "Gerando dump PostgreSQL..."
pg_dump \
  -h "$POSTGRES_HOST" \
  -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -Fc \
  -f "$dumpdir/${POSTGRES_DB}-${timestamp}.dump"

cat > "$manifest" <<EOF
hotspot-academia backup VM1
timestamp=$timestamp
postgres_db=$POSTGRES_DB
included=/backups/current
included=/source/configs
included=/source/rsyslog
included=/source/portal-data
EOF

if restic snapshots >/dev/null 2>&1; then
  :
elif restic cat config >/dev/null 2>&1; then
  echo "Repositorio restic ja existe, mas nao foi possivel listar snapshots." >&2
  echo "Verifique se RESTIC_PASSWORD no .env da VM1 e a mesma senha usada no 'restic init'." >&2
  exit 1
else
  echo "Inicializando repositorio restic..."
  restic init
fi

echo "Criando snapshot restic criptografado..."
restic backup \
  "$workdir" \
  /source/configs \
  /source/rsyslog \
  /source/portal-data \
  --tag hotspot-academia \
  --tag vm1

echo "Aplicando retencao..."
restic forget \
  --tag hotspot-academia \
  --tag vm1 \
  --keep-daily "$RESTIC_KEEP_DAILY" \
  --keep-weekly "$RESTIC_KEEP_WEEKLY" \
  --keep-monthly "$RESTIC_KEEP_MONTHLY" \
  --prune

echo "Backup VM1 concluido."
