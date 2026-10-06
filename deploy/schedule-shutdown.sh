#!/bin/bash
# Install one shared UTC deadline on both Pis; no battery gauge is assumed.
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run as root'; exit 1; }
deadline="$(date -u -d "${1:-+5 hours}" '+%Y-%m-%d %H:%M:%S UTC')"
remaining="$(( $(date -d "$deadline" +%s) - $(date +%s) ))"
test "$remaining" -gt 0 && test "$remaining" -le 43200 || {
    echo 'Deadline must be in the next 12 hours'; exit 2;
}
directory=/etc/systemd/system
umask 022
cat > "$directory/.robotcar-battery-shutdown.service.next" <<'UNIT'
[Unit]
Description=Power off Robotcar before the battery deadline

[Service]
Type=oneshot
ExecStart=/usr/bin/systemctl --no-block poweroff
UNIT
cat > "$directory/.robotcar-battery-shutdown.timer.next" <<UNIT
[Unit]
Description=One-time Robotcar battery deadline

[Timer]
OnCalendar=$deadline
AccuracySec=1s
RandomizedDelaySec=0
Persistent=true
Unit=robotcar-battery-shutdown.service

[Install]
WantedBy=timers.target
UNIT
for kind in service timer; do
    path="$directory/robotcar-battery-shutdown.$kind"
    sync -f "$directory/.robotcar-battery-shutdown.$kind.next"
    mv "$directory/.robotcar-battery-shutdown.$kind.next" "$path"
done
sync -f "$directory"
systemd-analyze verify "$directory/robotcar-battery-shutdown.service" "$directory/robotcar-battery-shutdown.timer"
systemctl daemon-reload
systemctl enable robotcar-battery-shutdown.timer
systemctl restart robotcar-battery-shutdown.timer
systemctl show robotcar-battery-shutdown.timer -p ActiveState -p NextElapseUSecRealtime
echo "Scheduled poweroff: $deadline"
