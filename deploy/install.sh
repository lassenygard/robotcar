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
    systemctl stop robotcar-motor robotcar@lidar robotcar@lidarfeed
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
if [ "$role" = sensors ]; then
    camera_dropin=/etc/systemd/system/robotcar@camera.service.d
    install -d -m 755 "$camera_dropin"
    install -m 644 "$release_dir/deploy/robotcar-camera-watchdog.conf" "$camera_dropin/.10-watchdog.conf.next"
    sync -f "$camera_dropin/.10-watchdog.conf.next"
    mv "$camera_dropin/.10-watchdog.conf.next" "$camera_dropin/10-watchdog.conf"
    sync -f "$camera_dropin"
fi
install -m 644 "$release_dir/deploy/80-robotcar-lidar.rules" /etc/udev/rules.d/
printf 'd /run/robotcar 0700 pi pi -\n' > /etc/tmpfiles.d/robotcar.conf
chmod 600 /etc/robotcar/robotcar.env
udevadm control --reload-rules
systemctl daemon-reload
if [ "$role" = motor ]; then
    systemctl enable robotcar-motor
    systemctl start robotcar-motor
    if grep -qx 'LIDAR_FEED_ENABLED=1' /etc/robotcar/robotcar.env; then
        systemctl enable robotcar@lidar robotcar@lidarfeed
        systemctl start robotcar@lidar robotcar@lidarfeed
    else
        systemctl disable --now robotcar@lidar robotcar@lidarfeed
    fi
else
    systemctl enable robotcar@camera robotcar@vision robotcar@lidar robotcar@mapworker robotcar@webapp
    systemctl start robotcar@camera robotcar@vision robotcar@lidar robotcar@mapworker robotcar@webapp
fi
