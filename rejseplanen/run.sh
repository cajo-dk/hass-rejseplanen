#!/usr/bin/with-contenv bashio
set -eu

export REJSEPLANEN_ACCESS_ID="$(bashio::config 'rejseplanen_access_id')"
export MQTT_HOST="$(bashio::config 'mqtt_host')"
export MQTT_PORT="$(bashio::config 'mqtt_port')"
export MQTT_TOPIC="$(bashio::config 'mqtt_topic')"
export MQTT_USERNAME="$(bashio::config 'mqtt_username')"
export MQTT_PASSWORD="$(bashio::config 'mqtt_password')"
export MQTT_CLIENT_ID="$(bashio::config 'mqtt_client_id')"
export MQTT_QOS="$(bashio::config 'mqtt_qos')"
export MQTT_TLS="$(bashio::config 'mqtt_tls')"
export REJSEPLANEN_MAX_JOURNEYS="$(bashio::config 'rejseplanen_max_journeys')"
export REJSEPLANEN_DURATION="$(bashio::config 'rejseplanen_duration')"

while true; do
  python3 /app/app.py 8695035 --cat-out Re --compact-data --mqtt-on || true
  sleep 60
done
