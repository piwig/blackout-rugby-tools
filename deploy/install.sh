#!/usr/bin/env bash
set -euo pipefail
release="${1:?Absolute release path required}"
case "$release" in /opt/brt/releases/*) ;; *) echo 'Release path rejected' >&2; exit 1;; esac
test -d "$release/server"
test -f "$release/web/dist/index.html"
id brt >/dev/null 2>&1 || useradd --system --home /var/lib/brt --shell /usr/sbin/nologin brt
install -d -m 700 -o brt -g brt /var/lib/brt
install -d -m 700 /opt/brt/backups
test -x /opt/brt/venv/bin/python || python3 -m venv /opt/brt/venv
/opt/brt/venv/bin/python -m pip install --quiet -r "$release/requirements.txt"
ln -sfn "$release" /opt/brt/current
install -m 644 "$release/deploy/brt.service" /etc/systemd/system/brt.service
install -m 644 "$release/deploy/brt-backup.service" /etc/systemd/system/brt-backup.service
install -m 644 "$release/deploy/brt-backup.timer" /etc/systemd/system/brt-backup.timer
systemctl daemon-reload
systemctl enable --now brt.service brt-backup.timer
systemctl restart brt.service
systemctl start brt-backup.service
systemctl is-active brt
