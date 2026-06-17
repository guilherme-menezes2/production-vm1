#!/usr/bin/env sh
set -eu

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY nao definido}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD nao definido}"

target="/restore-test/latest"
rm -rf "$target"
mkdir -p "$target"

restic restore latest --target "$target" --tag hotspot-academia --tag vm1
find "$target" -type f | head -n 20
echo "Restore test concluido em $target"
