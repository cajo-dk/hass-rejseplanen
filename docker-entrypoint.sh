#!/bin/sh
set -eu

while true; do
  python /app/fetch_departure_board.py 8695035 --cat-out Re --compact-data --mqtt-on || true
  sleep 60
done
