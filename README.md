# hass-rejseplanen

Home Assistant add-on repository with one add-on: **Rejseplanen Fetcher**.

The add-on fetches departures from Rejseplanen, filters by regional train category (`catOut=Re`), compacts the data for dashboards, wraps it in a status payload, and publishes it to MQTT every minute.

## Repository structure

```text
hass-rejseplanen/
├── repository.yaml
└── rejseplanen/
    ├── config.json
    ├── Dockerfile
    ├── run.sh
    └── app.py
```

## What it runs

Every 60 seconds, the add-on runs:

```bash
python3 /app/app.py 8695035 --cat-out Re --compact-data --mqtt-on
```

## MQTT payload format

Published payload:

```json
{
  "count": -1,
  "items": [],
  "updated": "2026-02-13T17:00:00+01:00",
  "ok": false,
  "error": null
}
```

On success:
- `ok = true`
- `count = number of items`
- `items = compact departures array`
- `error = null`

On error:
- `ok = false`
- `count = -1`
- `items = -1`
- `error = error message`

MQTT publishing uses `retain=true`.

## Compact item fields

Each item in `items` contains:
- `trainId`
- `direction`
- `departs`
- `plannedDate`
- `plannedTime`
- `actualDate`
- `actualTime`
- `status` (`on_time`, `delayed`, `cancelled`)

## Home Assistant configuration

Configure these options in the add-on UI:

- `rejseplanen_access_id` (required)
- `mqtt_host` (required)
- `mqtt_port` (default: `1883`)
- `mqtt_topic` (required)
- `mqtt_username` (optional)
- `mqtt_password` (optional)
- `mqtt_client_id` (optional)
- `mqtt_qos` (default: `0`)
- `mqtt_tls` (default: `false`)
- `rejseplanen_max_journeys` (default: `80`)
- `rejseplanen_duration` (default: `60`)

## Install in Home Assistant

1. Go to **Settings -> Add-ons -> Add-on Store**.
2. Add this repository URL:
   - `https://github.com/cajo-dk/hass-rejseplanen`
3. Install **Rejseplanen Fetcher**.
4. Fill in configuration values.
5. Start the add-on.

## Notes

- Local `$env` is ignored in git and not used by Home Assistant add-on runtime.
- Runtime config comes from Home Assistant add-on options and is exported by `run.sh`.
