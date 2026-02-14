#!/usr/bin/env python3
"""Resolve a Rejseplanen station/stop name to location IDs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://www.rejseplanen.dk/api/location.name"
ENV_FILES = ("$env", ".env")


def debug_log(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[debug] {message}", file=sys.stderr)


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def listify(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def load_access_id_from_env_files(debug: bool = False) -> str | None:
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
                    if key.strip() != "REJSEPLANEN_ACCESS_ID":
                        continue
                    value = value.strip().strip("'").strip('"')
                    if value:
                        debug_log(debug, f"Loaded access id from {path}.")
                        return value
        except OSError as exc:
            debug_log(debug, f"Could not read {path}: {exc}")
    return None


def resolve_access_id(cli_value: str | None, debug: bool = False) -> str | None:
    if cli_value:
        debug_log(debug, "Using access id from --access-id.")
        return cli_value

    env_value = os.getenv("REJSEPLANEN_ACCESS_ID")
    if env_value:
        debug_log(debug, "Using access id from REJSEPLANEN_ACCESS_ID environment variable.")
        return env_value

    return load_access_id_from_env_files(debug=debug)


def fetch_location_data(
    access_id: str,
    query: str,
    max_results: int,
    lang: str,
    location_type: str,
    debug: bool = False,
) -> dict:
    params = {
        "accessId": access_id,
        "input": query,
        "maxNo": str(max_results),
        "format": "json",
        "lang": lang,
        "type": location_type,
    }
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


def extract_location_records(payload: dict) -> list[tuple[str, dict]]:
    records: list[tuple[str, dict]] = []

    for item in listify(payload.get("stopLocationOrCoordLocation")):
        if not isinstance(item, dict):
            continue
        for location_kind, location_obj in item.items():
            if isinstance(location_obj, dict):
                records.append((location_kind, location_obj))

    location_list = payload.get("LocationList")
    if isinstance(location_list, dict):
        for location_kind in ("StopLocation", "CoordLocation", "POI", "Address"):
            for location_obj in listify(location_list.get(location_kind)):
                if isinstance(location_obj, dict):
                    records.append((location_kind, location_obj))

    return records


def normalize_locations(payload: dict) -> list[dict]:
    records = extract_location_records(payload)
    normalized = []
    for location_kind, location in records:
        location_type = location.get("type")
        if not location_type:
            location_type = "S" if location_kind == "StopLocation" else location_kind
        normalized.append(
            {
                "kind": location_kind,
                "id": location.get("id"),
                "extId": location.get("extId"),
                "name": location.get("name"),
                "type": location_type,
                "weight": location.get("weight"),
                "lat": location.get("lat"),
                "lon": location.get("lon"),
            }
        )
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find Rejseplanen station/stop IDs by name."
    )
    parser.add_argument("name", help="Station/stop search text, e.g. 'København H'")
    parser.add_argument(
        "--access-id",
        default=None,
        help="Rejseplanen API accessId (or set REJSEPLANEN_ACCESS_ID).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum number of results to return (default: 10).",
    )
    parser.add_argument(
        "--lang",
        default="da",
        help="Response language, e.g. da or en (default: da).",
    )
    parser.add_argument(
        "--type",
        default="S",
        choices=["A", "ALL", "AP", "P", "S", "SA", "SP"],
        help="Location type filter used by location.name (default: S).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print request and parsing debug logs to stderr.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print the full API payload instead of only normalized location rows.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    access_id = resolve_access_id(args.access_id, debug=args.debug)

    if not access_id:
        print(
            "Missing accessId. Pass --access-id, set REJSEPLANEN_ACCESS_ID, or add it in $env/.env.",
            file=sys.stderr,
        )
        return 2

    try:
        payload = fetch_location_data(
            access_id=access_id,
            query=args.name,
            max_results=args.max_results,
            lang=args.lang,
            location_type=args.type,
            debug=args.debug,
        )
    except urllib.error.HTTPError as exc:
        print(format_http_error(exc), file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1
    except TimeoutError:
        print("Request timed out.", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Failed to decode API response as JSON: {exc}", file=sys.stderr)
        return 1

    debug_log(args.debug, f"Response top-level keys: {sorted(payload.keys())}")

    if args.raw:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if payload.get("errorCode"):
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    matches = normalize_locations(payload)
    debug_log(args.debug, f"Normalized location candidates: {len(matches)}")

    print(
        json.dumps(
            {
                "query": args.name,
                "matches": matches,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
