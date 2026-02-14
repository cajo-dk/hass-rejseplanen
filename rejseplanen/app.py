#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from paho.mqtt import publish as mqtt_publish

API_URL = "https://www.rejseplanen.dk/api/departureBoard"


def parse_departure_datetime(date_value: object, time_value: object) -> dt.datetime | None:
    if not isinstance(date_value, str) or not isinstance(time_value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(f"{date_value} {time_value}", fmt)
        except ValueError:
            continue
    return None


def compact_departure_data(payload: dict, cat_out_filter: str | None = None) -> list[dict]:
    departures = payload.get("Departure")
    if departures is None:
        return []
    if not isinstance(departures, list):
        departures = [departures]

    rows: list[dict] = []
    for dep in departures:
        if not isinstance(dep, dict):
            continue

        cat_out = dep.get("ProductAtStop", {}).get("catOut") if isinstance(dep.get("ProductAtStop"), dict) else None
        if (
            isinstance(cat_out_filter, str)
            and cat_out_filter
            and isinstance(cat_out, str)
            and cat_out.lower() != cat_out_filter.lower()
        ):
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

        rows.append(
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
    return rows


def build_payload(items: list[dict] | None = None, error: str | None = None) -> dict:
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
    values = items or []
    payload["count"] = len(values)
    payload["items"] = values
    payload["ok"] = True
    return payload


def fetch_departure_board(access_id: str, stop_id: str, max_journeys: int, duration: int) -> dict:
    params = {
        "accessId": access_id,
        "id": stop_id,
        "format": "json",
        "type": "DEP",
        "duration": str(duration),
        "lang": "da",
        "maxJourneys": str(max_journeys),
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def publish_payload(payload: dict) -> None:
    host = os.getenv("MQTT_HOST")
    topic = os.getenv("MQTT_TOPIC")
    if not host:
        raise RuntimeError("Missing MQTT_HOST")
    if not topic:
        raise RuntimeError("Missing MQTT_TOPIC")

    port = int(os.getenv("MQTT_PORT", "1883"))
    qos = int(os.getenv("MQTT_QOS", "0"))
    client_id = os.getenv("MQTT_CLIENT_ID", "")
    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD", "")
    use_tls = os.getenv("MQTT_TLS", "").strip().lower() in {"1", "true", "yes", "on"}

    auth = {"username": username, "password": password} if username else None
    tls = {} if use_tls else None

    mqtt_publish.single(
        topic=topic,
        payload=json.dumps(payload, ensure_ascii=False),
        hostname=host,
        port=port,
        auth=auth,
        tls=tls,
        qos=qos,
        retain=True,
        client_id=client_id,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Rejseplanen compact departures and publish to MQTT.")
    parser.add_argument("stop_id", help="Station/stop id, e.g. 8600626")
    parser.add_argument("--cat-out", default=None, help="Filter by ProductAtStop.catOut, e.g. Re")
    parser.add_argument("--compact-data", action="store_true", help="Output compact dashboard data")
    parser.add_argument("--mqtt-on", action="store_true", help="Publish payload to MQTT")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mqtt_on and not args.compact_data:
        print(json.dumps(build_payload(error="--mqtt-on requires --compact-data"), ensure_ascii=False))
        return 1

    access_id = os.getenv("REJSEPLANEN_ACCESS_ID")
    stop_id = args.stop_id
    max_journeys = int(os.getenv("REJSEPLANEN_MAX_JOURNEYS", "80"))
    duration = int(os.getenv("REJSEPLANEN_DURATION", "60"))

    if not access_id:
        payload = build_payload(error="Missing REJSEPLANEN_ACCESS_ID")
        if args.mqtt_on:
            try:
                publish_payload(payload)
            except Exception:
                pass
        print(json.dumps(payload, ensure_ascii=False))
        return 1

    try:
        raw = fetch_departure_board(
            access_id=access_id,
            stop_id=stop_id,
            max_journeys=max_journeys,
            duration=duration,
        )
        if raw.get("errorCode"):
            raise RuntimeError(raw.get("errorText") or raw.get("errorCode"))

        if args.compact_data:
            compact = compact_departure_data(raw, cat_out_filter=args.cat_out)
            payload = build_payload(items=compact)
        else:
            payload = raw
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, RuntimeError) as exc:
        payload = build_payload(error=str(exc))

    if args.mqtt_on:
        try:
            publish_payload(payload)
        except Exception as exc:
            fallback = build_payload(error=str(exc))
            print(json.dumps(fallback, ensure_ascii=False))
            return 1

    print(json.dumps(payload, ensure_ascii=False))
    if isinstance(payload, dict) and payload.get("ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
