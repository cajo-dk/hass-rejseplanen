#!/bin/sh
set -eu

OPTIONS_FILE="/data/options.json"

read_option() {
  python3 - "$1" "$OPTIONS_FILE" <<'PY'
import json
import sys

key = sys.argv[1]
path = sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
value = data.get(key, "")
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PY
}

export REJSEPLANEN_ACCESS_ID="$(read_option rejseplanen_access_id)"
export REJSEPLANEN_STOP_ID="$(read_option rejseplanen_stop_id)"
export MQTT_HOST="$(read_option mqtt_host)"
export MQTT_PORT="$(read_option mqtt_port)"
export MQTT_TOPIC="$(read_option mqtt_topic)"
export MQTT_USERNAME="$(read_option mqtt_username)"
export MQTT_PASSWORD="$(read_option mqtt_password)"
export MQTT_CLIENT_ID="$(read_option mqtt_client_id)"
export MQTT_QOS="$(read_option mqtt_qos)"
export MQTT_TLS="$(read_option mqtt_tls)"
export REJSEPLANEN_MAX_JOURNEYS="$(read_option rejseplanen_max_journeys)"
export REJSEPLANEN_DURATION="$(read_option rejseplanen_duration)"

while true; do
  python3 /app/app.py "${REJSEPLANEN_STOP_ID:-8695035}" --cat-out Re --compact-data --mqtt-on || true
  sleep 60
done
