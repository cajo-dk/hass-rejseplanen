#!/usr/bin/env python3
"""Fetch a Rejseplanen departure board as JSON for a given stop/station ID."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://www.rejseplanen.dk/api/departureBoard"
ENV_FILES = ("$env", ".env")


def debug_log(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[debug] {message}", file=sys.stderr)


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_env_file_values(debug: bool = False) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in ENV_FILES:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[len("export ") :].strip()
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'").strip('"')
                    if value:
                        values[key] = value
            debug_log(debug, f"Loaded {len(values)} env values from {path}.")
        except OSError as exc:
            debug_log(debug, f"Could not read {path}: {exc}")
    return values


def resolve_env_value(keys: list[str], file_env: dict[str, str]) -> str | None:
    for key in keys:
        env_value = os.getenv(key)
        if env_value:
            return env_value
    for key in keys:
        file_value = file_env.get(key)
        if file_value:
            return file_value
    return None


def resolve_access_id(
    cli_value: str | None, file_env: dict[str, str], debug: bool = False
) -> str | None:
    if cli_value:
        debug_log(debug, "Using access id from --access-id.")
        return cli_value

    env_value = resolve_env_value(["REJSEPLANEN_ACCESS_ID"], file_env)
    if env_value:
        debug_log(debug, "Using access id from env config.")
        return env_value

    return None


def listify(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_departure_datetime(date_value: object, time_value: object) -> dt.datetime | None:
    if not isinstance(date_value, str) or not isinstance(time_value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(f"{date_value} {time_value}", fmt)
        except ValueError:
            continue
    return None


def compact_departure_data(payload: dict) -> list[dict]:
    compact_rows = []
    for dep in listify(payload.get("Departure")):
        if not isinstance(dep, dict):
            continue

        planned_date = dep.get("date")
        planned_time = dep.get("time")
        actual_date = dep.get("rtDate")
        actual_time = dep.get("rtTime")
        cancelled = bool(dep.get("cancelled", False))

        status = "on_time"
        if cancelled:
            status = "cancelled"
        else:
            planned_dt = parse_departure_datetime(planned_date, planned_time)
            actual_dt = parse_departure_datetime(actual_date, actual_time)
            if planned_dt and actual_dt and actual_dt > planned_dt:
                status = "delayed"

        compact_rows.append(
            {
                "trainId": dep.get("name"),
                "direction": dep.get("direction"),
                "departs": dep.get("stop"),
                "plannedDate": planned_date,
                "plannedTime": planned_time,
                "actualDate": actual_date,
                "actualTime": actual_time,
                "status": status,
            }
        )
    return compact_rows


def build_mqtt_payload(items: list[dict] | None = None, error: str | None = None) -> dict:
    updated = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    payload = {
        "count": -1,
        "items": [],
        "updated": updated,
        "ok": False,
        "error": None,
    }
    if error:
        payload["items"] = -1
        payload["error"] = error
        return payload
    rows = items or []
    payload["count"] = len(rows)
    payload["items"] = rows
    payload["ok"] = True
    return payload


def publish_payload_to_mqtt(
    payload: dict, file_env: dict[str, str], debug: bool = False
) -> None:
    host = resolve_env_value(["MQTT_HOST", "MQTT_BROKER", "MQTT_SERVER"], file_env)
    topic = resolve_env_value(["MQTT_TOPIC", "MQTT_PUB_TOPIC"], file_env)
    port_str = resolve_env_value(["MQTT_PORT"], file_env) or "1883"
    client_id = resolve_env_value(["MQTT_CLIENT_ID"], file_env) or ""
    username = resolve_env_value(["MQTT_USERNAME", "MQTT_USER"], file_env)
    password = resolve_env_value(["MQTT_PASSWORD", "MQTT_PASS"], file_env)
    qos_str = resolve_env_value(["MQTT_QOS"], file_env) or "0"
    retain = True
    use_tls = parse_bool(resolve_env_value(["MQTT_TLS"], file_env), default=False)

    if not host:
        raise RuntimeError("Missing MQTT host. Set MQTT_HOST in $env.")
    if not topic:
        raise RuntimeError("Missing MQTT topic. Set MQTT_TOPIC in $env.")

    try:
        port = int(port_str)
    except ValueError as exc:
        raise RuntimeError(f"Invalid MQTT_PORT value: {port_str}") from exc
    try:
        qos = int(qos_str)
    except ValueError as exc:
        raise RuntimeError(f"Invalid MQTT_QOS value: {qos_str}") from exc

    debug_log(
        debug,
        f"Publishing to MQTT host={host}:{port} topic={topic} qos={qos} retain={retain} tls={use_tls}",
    )

    try:
        from paho.mqtt import publish as mqtt_publish
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'paho-mqtt'. Install with: pip install paho-mqtt"
        ) from exc

    auth = None
    if username:
        auth = {"username": username, "password": password or ""}
        debug_log(debug, f"Using MQTT auth username={username} password={mask_secret(password or '')}")

    tls = {} if use_tls else None
    mqtt_publish.single(
        topic=topic,
        payload=json.dumps(payload, ensure_ascii=False),
        hostname=host,
        port=port,
        auth=auth,
        tls=tls,
        qos=qos,
        retain=retain,
        client_id=client_id,
    )


def fetch_departure_board(
    access_id: str,
    stop_id: str,
    max_journeys: int | None,
    duration: int,
    board_type: str,
    lang: str,
    debug: bool = False,
) -> dict:
    params = {
        "accessId": access_id,
        "id": stop_id,
        "format": "json",
        "type": board_type,
        "duration": str(duration),
        "lang": lang,
    }
    if max_journeys is not None:
        params["maxJourneys"] = str(max_journeys)

    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    debug_log(
        debug,
        "GET "
        + url.replace(
            urllib.parse.quote_plus(access_id),
            urllib.parse.quote_plus(mask_secret(access_id)),
        ),
    )
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def format_http_error(exc: urllib.error.HTTPError) -> str:
    body = ""
    try:
        body = exc.read().decode("utf-8").strip()
    except Exception:
        body = ""

    if not body:
        return f"HTTP error: {exc.code} {exc.reason}"

    try:
        parsed = json.loads(body)
        return f"HTTP error: {exc.code} {exc.reason}\n{json.dumps(parsed, ensure_ascii=False, indent=2)}"
    except json.JSONDecodeError:
        return f"HTTP error: {exc.code} {exc.reason}\n{body}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a Rejseplanen departure board in JSON format."
    )
    parser.add_argument("stop_id", help="Station/stop id from location.name")
    parser.add_argument(
        "--access-id",
        default=None,
        help="Rejseplanen API accessId (or set REJSEPLANEN_ACCESS_ID).",
    )
    parser.add_argument(
        "--max-journeys",
        type=int,
        default=20,
        help="Maximum number of departures to return (default: 20).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Time window in minutes (default: 60).",
    )
    parser.add_argument(
        "--type",
        default="DEP",
        choices=["DEP", "DEP_EQUIVS", "DEP_MAST", "DEP_STATION"],
        help="Departure board type (default: DEP).",
    )
    parser.add_argument(
        "--lang",
        default="da",
        help="Response language, e.g. da or en (default: da).",
    )
    parser.add_argument(
        "--cat-out",
        default=None,
        help="Filter departures by ProductAtStop.catOut (comma-separated), e.g. Re or IC,Re.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print request and response debug logs to stderr.",
    )
    parser.add_argument(
        "--compact-data",
        action="store_true",
        help="Output a compact dashboard-friendly data shape.",
    )
    parser.add_argument(
        "--mqtt-on",
        action="store_true",
        help="Publish compact data payload to MQTT (requires --compact-data).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mqtt_on and not args.compact_data:
        print("--mqtt-on requires --compact-data.", file=sys.stderr)
        return 2

    file_env = load_env_file_values(debug=args.debug)
    access_id = resolve_access_id(args.access_id, file_env=file_env, debug=args.debug)

    if not access_id:
        error_message = (
            "Missing accessId. Pass --access-id, set REJSEPLANEN_ACCESS_ID, or add it in $env/.env."
        )
        if args.mqtt_on:
            mqtt_payload = build_mqtt_payload(error=error_message)
            try:
                publish_payload_to_mqtt(mqtt_payload, file_env=file_env, debug=args.debug)
            except Exception as mqtt_exc:
                debug_log(args.debug, f"MQTT publish failed: {mqtt_exc}")
            print(json.dumps(mqtt_payload, ensure_ascii=False, indent=2))
            return 1
        print(error_message, file=sys.stderr)
        return 2

    processing_error: str | None = None
    payload: dict = {}
    try:
        payload = fetch_departure_board(
            access_id=access_id,
            stop_id=args.stop_id,
            max_journeys=args.max_journeys,
            duration=args.duration,
            board_type=args.type,
            lang=args.lang,
            debug=args.debug,
        )
    except urllib.error.HTTPError as exc:
        processing_error = format_http_error(exc)
    except urllib.error.URLError as exc:
        processing_error = f"Network error: {exc.reason}"
    except TimeoutError:
        processing_error = "Request timed out."
    except json.JSONDecodeError as exc:
        processing_error = f"Failed to decode API response as JSON: {exc}"

    if processing_error:
        if args.mqtt_on:
            mqtt_payload = build_mqtt_payload(error=processing_error)
            try:
                publish_payload_to_mqtt(mqtt_payload, file_env=file_env, debug=args.debug)
            except Exception as mqtt_exc:
                debug_log(args.debug, f"MQTT publish failed: {mqtt_exc}")
            print(json.dumps(mqtt_payload, ensure_ascii=False, indent=2))
            return 1
        print(processing_error, file=sys.stderr)
        return 1

    debug_log(args.debug, f"Response top-level keys: {sorted(payload.keys())}")

    if payload.get("errorCode"):
        processing_error = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.mqtt_on:
            mqtt_payload = build_mqtt_payload(error=processing_error)
            try:
                publish_payload_to_mqtt(mqtt_payload, file_env=file_env, debug=args.debug)
            except Exception as mqtt_exc:
                debug_log(args.debug, f"MQTT publish failed: {mqtt_exc}")
            print(json.dumps(mqtt_payload, ensure_ascii=False, indent=2))
            return 1
        print(processing_error, file=sys.stderr)
        return 1

    if args.cat_out:
        filters = {item.strip().lower() for item in args.cat_out.split(",") if item.strip()}
        departures = listify(payload.get("Departure"))
        before = len(departures)
        filtered = []
        for dep in departures:
            if not isinstance(dep, dict):
                continue
            cat_out = (
                dep.get("ProductAtStop", {}).get("catOut")
                if isinstance(dep.get("ProductAtStop"), dict)
                else None
            )
            if isinstance(cat_out, str) and cat_out.lower() in filters:
                filtered.append(dep)
        payload["Departure"] = filtered
        debug_log(
            args.debug,
            f"Filtered departures by catOut={sorted(filters)}: {before} -> {len(filtered)}",
        )

    if args.compact_data:
        compact = compact_departure_data(payload)
        debug_log(args.debug, f"Compact rows produced: {len(compact)}")
        if args.mqtt_on:
            mqtt_payload = build_mqtt_payload(items=compact)
            try:
                publish_payload_to_mqtt(mqtt_payload, file_env=file_env, debug=args.debug)
            except Exception as mqtt_exc:
                mqtt_payload = build_mqtt_payload(error=str(mqtt_exc))
                print(json.dumps(mqtt_payload, ensure_ascii=False, indent=2))
                return 1
            print(json.dumps(mqtt_payload, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps(compact, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
