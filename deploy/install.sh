#!/bin/bash
set -euo pipefail
role="${1:-}"
case "$role" in motor|sensors) ;; *) echo 'Usage: sudo bash deploy/install.sh motor|sensors'; exit 2;; esac
test "$(id -u)" = 0 || { echo 'Run as root'; exit 1; }
source_dir="$(cd "$(dirname "$0")/.." && pwd)"
test -f /etc/robotcar/robotcar.env || { echo 'Create private /etc/robotcar/robotcar.env first; see docs/INSTALL.md'; exit 1; }
install -d -m 755 /opt/robotcar
install -d -o pi -g pi -m 700 /run/robotcar /var/lib/robotcar
release_dir="$(python3 "$source_dir/deploy/release.py" stage "$source_dir")"
if [ "$role" = motor ]; then
    systemctl stop robotcar-motor
else
    systemctl stop robotcar@camera robotcar@vision robotcar@lidar robotcar@mapworker robotcar@webapp
fi
python3 "$source_dir/deploy/release.py" activate "$release_dir"
for unit in robotcar-motor.service robotcar@.service; do
    install -m 644 "$release_dir/deploy/$unit" "/etc/systemd/system/.$unit.next"
    sync -f "/etc/systemd/system/.$unit.next"
    mv "/etc/systemd/system/.$unit.next" "/etc/systemd/system/$unit"
done
sync -f /etc/systemd/system
install -m 644 "$release_dir/deploy/80-robotcar-lidar.rules" /etc/udev/rules.d/
printf 'd /run/robotcar 0700 pi pi -\n' > /etc/tmpfiles.d/robotcar.conf
chmod 600 /etc/robotcar/robotcar.env
udevadm control --reload-rules
systemctl daemon-reload
if [ "$role" = motor ]; then
    systemctl enable robotcar-motor
    systemctl start robotcar-motor
else
    systemctl enable robotcar@camera robotcar@vision robotcar@lidar robotcar@mapworker robotcar@webapp
    systemctl start robotcar@camera robotcar@vision robotcar@lidar robotcar@mapworker robotcar@webapp
fi
