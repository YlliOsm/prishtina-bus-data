#!/usr/bin/env bash
set -euo pipefail
PW='ylli2008'

printf '%s
' "$PW" | sudo -S sh -c '
  set -e
  install -m 644 /home/pc-agent/prishtina-bus-data/prishtina-bus-tracker.service /etc/systemd/system/prishtina-bus-tracker.service
  install -m 644 /home/pc-agent/prishtina-bus-data/prishtina-bus-tracker.timer /etc/systemd/system/prishtina-bus-tracker.timer
  chmod 755 /home/pc-agent/prishtina-bus-data/run_tracker.sh
  systemctl daemon-reload
  systemctl enable --now prishtina-bus-tracker.timer
'

(crontab -l 2>/dev/null | sed '/prishtina-bus-tracker/d' | crontab -) || true

printf '%s
' "$PW" | sudo -S systemctl start prishtina-bus-tracker.service
sleep 2

systemctl is-enabled prishtina-bus-tracker.timer
systemctl status prishtina-bus-tracker.timer --no-pager -l | sed -n '1,20p'

echo '---CRONTAB---'
crontab -l 2>/dev/null || true

echo '---FILES---'
ls -l /home/pc-agent/prishtina-bus-data/snapshots/003/023.json \
      /home/pc-agent/prishtina-bus-data/csv_snapshots/003/023.csv \
      /home/pc-agent/prishtina-bus-data/csv_active/003/023.csv \
      /home/pc-agent/prishtina-bus-data/lines_static.json \
      /home/pc-agent/prishtina-bus-data/lines_static.csv

echo '---LOG---'
tail -n 20 /tmp/prishtina-bus-tracker.log || true
