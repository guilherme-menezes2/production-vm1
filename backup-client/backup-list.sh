#!/usr/bin/env sh
set -eu

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY nao definido}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD nao definido}"

restic snapshots --tag hotspot-academia --tag vm1
