#!/usr/bin/env python3
"""Small smoke-test helper for Person 2 pipeline flows."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


def build_event(level: str, message: str, source: str, raw: str | None = None) -> dict:
    return {
        "source": source,
        "level": level,
        "message": message,
        "raw": raw or message,
    }


def post_json(url: str, payload: dict | list[dict], insecure: bool = False) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    context = None
    if insecure and urlparse(url).scheme == "https":
        context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=10, context=context) as response:
        return response.status, response.read().decode("utf-8")


def send_high(url: str, source: str, insecure: bool, message: str) -> None:
    payload = build_event(
        level="fatal",
        source=source,
        message=message,
    )
    status, body = post_json(url, payload, insecure=insecure)
    print(f"high-tier status={status}")
    print(body)


def send_medium(
    url: str,
    source: str,
    count: int,
    delay_seconds: float,
    insecure: bool,
    level: str,
    message_template: str,
) -> None:
    for idx in range(1, count + 1):
        payload = build_event(
            level=level,
            source=source,
            message=message_template.format(n=idx),
        )
        status, body = post_json(url, payload, insecure=insecure)
        print(f"medium-tier {idx}/{count} status={status}")
        print(body)
        if idx != count and delay_seconds > 0:
            time.sleep(delay_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test Person 2 log flows.")
    parser.add_argument(
        "--url",
        default="https://localhost/api/ingest",
        help="Pipeline ingest URL.",
    )
    parser.add_argument(
        "--source",
        default="person2-smoke",
        help="Source value to include in emitted logs.",
    )
    parser.add_argument(
        "--mode",
        choices=["high", "medium", "both"],
        default="both",
        help="Which smoke flow to run.",
    )
    parser.add_argument(
        "--medium-count",
        type=int,
        default=5,
        help="How many medium-tier logs to send.",
    )
    parser.add_argument(
        "--medium-delay",
        type=float,
        default=0.2,
        help="Delay between medium-tier log posts.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification for local HTTPS testing.",
    )
    parser.add_argument(
        "--high-message",
        default="FATAL: too many connections for role postgres",
        help="Message to send for the high-tier test event.",
    )
    parser.add_argument(
        "--medium-level",
        default="warn",
        help="Level to use for medium-tier test events.",
    )
    parser.add_argument(
        "--medium-message",
        default="database connection timeout #{n}",
        help="Template for medium-tier messages. Use {n} for the event number.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.mode in {"high", "both"}:
            send_high(args.url, args.source, args.insecure, args.high_message)
        if args.mode in {"medium", "both"}:
            send_medium(
                args.url,
                args.source,
                args.medium_count,
                args.medium_delay,
                args.insecure,
                args.medium_level,
                args.medium_message,
            )
        return 0
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
