#!/usr/bin/env bash
set -euo pipefail
umask 077
set -a
. /etc/restic-r2.env
set +a
export RESTIC_CACHE_DIR=/var/cache/restic
paths=(/opt/brt/backups /opt/brt/source)
test ! -d /etc/brt || paths+=(/etc/brt)
restic --retry-lock 10m backup "${paths[@]}" --tag brt --quiet
