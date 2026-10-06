#!/bin/sh
# Run on the existing nginx edge after DNS points to its public address.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo.' >&2; exit 1; }
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backup=/var/backups/robotcar-edge/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup"
chmod 700 "$backup"
paths='etc/nginx/sites-available/robotcar.nygardene.no.conf
etc/nginx/sites-enabled/robotcar.nygardene.no.conf
etc/nginx/snippets/robotcar-proxy.conf
etc/nginx/sites-enabled/nygardene-disabled-apps.conf'
for path in $paths; do
    if [ -e "/$path" ] || [ -L "/$path" ]; then
        mkdir -p "$backup/$(dirname -- "$path")"
        cp -a "/$path" "$backup/$path"
    fi
done
rollback() {
    trap - EXIT HUP INT TERM
    for path in $paths; do
        rm -f "/$path"
        if [ -e "$backup/$path" ] || [ -L "$backup/$path" ]; then
            cp -a "$backup/$path" "/$path"
        fi
    done
    nginx -t && systemctl reload nginx
    echo "Edge setup failed; configuration restored from $backup" >&2
}
trap rollback EXIT
trap 'exit 1' HUP INT TERM

# This host used to be explicitly retired. Preserve the other retired hosts.
python3 - <<'PY'
from pathlib import Path
path = Path('/etc/nginx/sites-enabled/nygardene-disabled-apps.conf')
if path.exists():
    text = path.read_text()
    path.write_text(text.replace(' robotcar.nygardene.no', ''))
PY
install -d /var/www/certbot /etc/nginx/snippets
install -m 644 "$source_dir/robotcar.nginx.conf" /etc/nginx/snippets/robotcar-proxy.conf
cat > /etc/nginx/sites-available/robotcar.nygardene.no.conf <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name robotcar.nygardene.no;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type text/plain;
        try_files $uri =404;
    }
    location / { return 503; }
}
NGINX
ln -sfn /etc/nginx/sites-available/robotcar.nygardene.no.conf /etc/nginx/sites-enabled/robotcar.nygardene.no.conf
nginx -t
systemctl reload nginx
certbot certonly --non-interactive --webroot -w /var/www/certbot \
    --cert-name robotcar.nygardene.no -d robotcar.nygardene.no
install -m 644 "$source_dir/robotcar.nygardene.no.conf" /etc/nginx/sites-available/robotcar.nygardene.no.conf
nginx -t
systemctl reload nginx
trap - EXIT HUP INT TERM
echo "Robotcar HTTPS configured. Previous nginx files: $backup"
