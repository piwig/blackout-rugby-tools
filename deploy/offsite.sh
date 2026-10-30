#!/usr/bin/env bash
set -euo pipefail
umask 077
set -a
. /etc/restic-r2.env
set +a
export RESTIC_CACHE_DIR=/var/cache/restic
restic --retry-lock 10m backup /opt/brt/backups /opt/brt/source --tag brt --quiet
