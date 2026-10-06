#!/bin/bash
set -euo pipefail
role="${1:-}"
case "$role" in motor|sensors) ;; *) echo 'Usage: sudo bash deploy/install.sh motor|sensors'; exit 2;; esac
test "$(id -u)" = 0 || { echo 'Run as root'; exit 1; }
source_dir="$(cd "$(dirname "$0")/.." && pwd)"
test -f /etc/robotcar/robotcar.env || { echo 'Create private /etc/robotcar/robotcar.env first; see docs/INSTALL.md'; exit 1; }
install -d -m 755 /opt/robotcar
install -d -o pi -g pi -m 700 /run/robotcar /var/lib/robotcar
if [ "$source_dir" != /opt/robotcar ]; then
    cp -a "$source_dir/robotcar" /opt/robotcar/
fi
cp "$source_dir/deploy/robotcar-motor.service" "$source_dir/deploy/robotcar@.service" /etc/systemd/system/
install -m 644 "$source_dir/deploy/80-robotcar-lidar.rules" /etc/udev/rules.d/
printf 'd /run/robotcar 0700 pi pi -\n' > /etc/tmpfiles.d/robotcar.conf
chmod 600 /etc/robotcar/robotcar.env
udevadm control --reload-rules
systemctl daemon-reload
if [ "$role" = motor ]; then
    systemctl enable robotcar-motor
    systemctl restart robotcar-motor
else
    systemctl enable robotcar@camera robotcar@vision robotcar@lidar robotcar@mapworker robotcar@webapp
    systemctl restart robotcar@camera robotcar@vision robotcar@lidar robotcar@mapworker robotcar@webapp
fi
