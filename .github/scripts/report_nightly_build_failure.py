#!/usr/bin/env python3
"""
Called by GitHub Actions when the nightly build fails.

Posts to Slack when ``SLACK_WEBHOOK_URL`` is configured (optional).
"""

from __future__ import annotations

import http.client
import json
import os
import sys

from urllib.parse import urlparse


def _slack_webhook_target(webhook: str) -> tuple[str, str]:
    parsed = urlparse(webhook)
    if parsed.scheme != "https":
        msg = f"Slack webhook must use HTTPS, not {parsed.scheme!r}"
        raise ValueError(msg)
    if not parsed.hostname or not parsed.hostname.endswith("slack.com"):
        msg = f"Unexpected Slack webhook host: {parsed.hostname!r}"
        raise ValueError(msg)
    if not parsed.path:
        raise ValueError("Slack webhook URL must include a path")
    path = parsed.path
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return parsed.hostname, path


def post_slack_message(webhook: str, text: str) -> int:
    host, path = _slack_webhook_target(webhook)
    body = json.dumps({"text": text}).encode()
    conn = http.client.HTTPSConnection(host, timeout=30)
    try:
        conn.request(
            "POST",
            path,
            body,
            {"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = response.read().decode()
        print("Slack responded with:", response.status, payload)
        if response.status >= 400:
            return 1
    finally:
        conn.close()
    return 0


def main() -> int:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("SLACK_WEBHOOK_URL is not set; skipping Slack notification.")
        return 0

    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    text = (
        f"Nightly Wagtail main build failed for {repository}. "
        f"See https://github.com/{repository}/actions/runs/{run_id}"
    )
    try:
        return post_slack_message(webhook, text)
    except (ValueError, OSError) as exc:
        print("Slack notification failed:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
