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
export LOG_LEVEL="$(read_option log_level)"
export REJSEPLANEN_MAX_JOURNEYS="$(read_option rejseplanen_max_journeys)"
export REJSEPLANEN_DURATION="$(read_option rejseplanen_duration)"
export POLL_INTERVAL_MINUTES="$(read_option poll_interval_minutes)"

LOG_LEVEL="$(printf '%s' "${LOG_LEVEL:-INFO}" | tr '[:lower:]' '[:upper:]')"

case "${LOG_LEVEL}" in
  DEBUG|INFO|WARN|ERROR)
    ;;
  *)
    LOG_LEVEL="INFO"
    ;;
esac

level_to_num() {
  case "$1" in
    DEBUG) echo 10 ;;
    INFO) echo 20 ;;
    WARN) echo 30 ;;
    ERROR) echo 40 ;;
    *) echo 20 ;;
  esac
}

CURRENT_LOG_LEVEL_NUM="$(level_to_num "${LOG_LEVEL}")"

log() {
  level="$1"
  shift
  level_num="$(level_to_num "${level}")"
  if [ "${level_num}" -lt "${CURRENT_LOG_LEVEL_NUM}" ]; then
    return 0
  fi
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "${level}" "$*"
}

case "${POLL_INTERVAL_MINUTES:-}" in
  ''|*[!0-9]*)
    POLL_INTERVAL_MINUTES=60
    ;;
esac

if [ "${POLL_INTERVAL_MINUTES}" -lt 1 ]; then
  POLL_INTERVAL_MINUTES=1
fi

while true; do
  if output="$(python3 /app/app.py "${REJSEPLANEN_STOP_ID:-8695035}" --cat-out Re --compact-data --mqtt-on 2>&1)"; then
    if [ "${LOG_LEVEL}" = "DEBUG" ] && [ -n "${output}" ]; then
      log DEBUG "Call output: ${output}"
    fi
  else
    rc=$?
    log WARN "Call failed with exit code ${rc}."
    if [ "${LOG_LEVEL}" = "DEBUG" ] && [ -n "${output}" ]; then
      log DEBUG "Call output: ${output}"
    fi
  fi
  sleep "$((POLL_INTERVAL_MINUTES * 60))"
done
