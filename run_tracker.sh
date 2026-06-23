#!/usr/bin/env bash
set -euo pipefail
cd /home/pc-agent/prishtina-bus-data
exec /usr/bin/flock /tmp/prishtina-bus-tracker.lock /usr/bin/python3 /home/pc-agent/prishtina-bus-data/collect.py >> /tmp/prishtina-bus-tracker.log 2>&1
