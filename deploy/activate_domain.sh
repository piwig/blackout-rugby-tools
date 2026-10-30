#!/usr/bin/env bash
set -euo pipefail
# Run after the Cloudflare A record brt.bordebat.fr points to this VPS.
getent ahostsv4 brt.bordebat.fr >/dev/null
install -d -m 755 /var/www/letsencrypt
install -m 644 /opt/brt/current/deploy/nginx.conf /etc/nginx/sites-available/brt.conf
ln -sfn /etc/nginx/sites-available/brt.conf /etc/nginx/sites-enabled/brt.conf
nginx -t
systemctl reload nginx
certbot certonly --webroot -w /var/www/letsencrypt -d brt.bordebat.fr --non-interactive
install -m 644 /opt/brt/current/deploy/brt-cloudflare-realip.conf /etc/nginx/snippets/brt-cloudflare-realip.conf
install -m 644 /opt/brt/current/deploy/nginx.tls.conf /etc/nginx/sites-available/brt.conf
nginx -t
systemctl reload nginx
curl --fail --silent --show-error --resolve brt.bordebat.fr:443:127.0.0.1 https://brt.bordebat.fr/api/health
