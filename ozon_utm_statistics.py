#!/usr/bin/env python3
"""Download Ozon external traffic analytics by UTM tags."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


API_BASE_URL = "https://api-performance.ozon.ru"
TOKEN_PATH = "/api/client/token"
REPORT_PATH = "/api/client/vendors/statistics"
REPORT_TYPE = "TRAFFIC_SOURCES"


class OzonApiError(RuntimeError):
    """Raised when Ozon Performance API returns an error response."""


@dataclass(frozen=True)
class OzonCredentials:
    client_id: str
    client_secret: str


def request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise OzonApiError(f"{method} {url} failed: HTTP {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise OzonApiError(f"{method} {url} failed: {error.reason}") from error

    if not raw:
        return {}

    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise OzonApiError(f"{method} {url} returned non-JSON response") from error


def get_access_token(credentials: OzonCredentials, base_url: str) -> str:
    response = request_json(
        "POST",
        f"{base_url}{TOKEN_PATH}",
        payload={
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "grant_type": "client_credentials",
        },
    )
    token = response.get("access_token")
    if not isinstance(token, str) or not token:
        raise OzonApiError(f"Token response does not contain access_token: {response}")
    return token


def submit_report(token: str, base_url: str, date_from: str, date_to: str) -> str:
    response = request_json(
        "POST",
        f"{base_url}{REPORT_PATH}",
        token=token,
        payload={
            "dateFrom": date_from,
            "dateTo": date_to,
            "type": REPORT_TYPE,
        },
    )
    uuid = response.get("UUID") or response.get("uuid")
    if not isinstance(uuid, str) or not uuid:
        raise OzonApiError(f"Report submit response does not contain UUID: {response}")
    return uuid


def get_report_status(token: str, base_url: str, uuid: str) -> dict[str, Any]:
    quoted_uuid = urllib.parse.quote(uuid, safe="")
    return request_json("GET", f"{base_url}{REPORT_PATH}/{quoted_uuid}", token=token)


def wait_report(
    token: str,
    base_url: str,
    uuid: str,
    *,
    poll_interval: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds

    while True:
        status = get_report_status(token, base_url, uuid)
        state = str(status.get("state", "")).upper()

        if state in {"OK", "DONE", "SUCCESS", "COMPLETED"}:
            return status

        if state in {"ERROR", "FAILED", "FAIL"}:
            error = status.get("error") or status
            raise OzonApiError(f"Report generation failed: {error}")

        if time.monotonic() >= deadline:
            raise TimeoutError(f"Report {uuid} was not ready after {timeout_seconds} seconds")

        print(f"Report {uuid}: state={state or 'UNKNOWN'}, waiting {poll_interval}s...", file=sys.stderr)
        time.sleep(poll_interval)


def choose_output_path(output: Path, response: urllib.response.addinfourl, url: str) -> Path:
    if output.suffix:
        return output

    filename = ""
    disposition = response.headers.get("Content-Disposition", "")
    for chunk in disposition.split(";"):
        key, _, value = chunk.strip().partition("=")
        if key.lower() == "filename":
            filename = value.strip("\"'")
            break

    if not filename:
        path_name = Path(urllib.parse.urlparse(url).path).name
        filename = path_name or "ozon_utm_statistics_report"

    return output / filename


def download_report(token: str, base_url: str, link: str, output: Path, timeout: int = 120) -> Path:
    url = urllib.parse.urljoin(f"{base_url}/", link)
    url_host = urllib.parse.urlparse(url).netloc
    api_host = urllib.parse.urlparse(base_url).netloc
    headers = {"Accept": "*/*"}
    if url_host == api_host:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            output_path = choose_output_path(output, response, url)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.read())
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise OzonApiError(f"Download failed: HTTP {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise OzonApiError(f"Download failed: {error.reason}") from error

    return output_path


def read_credentials() -> OzonCredentials:
    client_id = os.getenv("OZON_PERFORMANCE_CLIENT_ID", "").strip()
    client_secret = os.getenv("OZON_PERFORMANCE_CLIENT_SECRET", "").strip()

    missing = []
    if not client_id:
        missing.append("OZON_PERFORMANCE_CLIENT_ID")
    if not client_secret:
        missing.append("OZON_PERFORMANCE_CLIENT_SECRET")

    if missing:
        names = ", ".join(missing)
        raise OzonApiError(f"Set environment variables first: {names}")

    return OzonCredentials(client_id=client_id, client_secret=client_secret)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and download Ozon UTM/external traffic analytics report.",
    )
    parser.add_argument("--date-from", required=True, help="Start date in YYYY-MM-DD format")
    parser.add_argument("--date-to", required=True, help="End date in YYYY-MM-DD format")
    parser.add_argument(
        "--output",
        default="reports",
        type=Path,
        help="Output file or directory. Default: reports",
    )
    parser.add_argument(
        "--uuid",
        help="Existing report UUID. If passed, the script skips report creation and only waits/downloads.",
    )
    parser.add_argument("--base-url", default=API_BASE_URL, help=f"API base URL. Default: {API_BASE_URL}")
    parser.add_argument("--poll-interval", default=10, type=int, help="Polling interval in seconds")
    parser.add_argument("--timeout", default=1800, type=int, help="Report generation timeout in seconds")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    credentials = read_credentials()

    token = get_access_token(credentials, args.base_url)
    uuid = args.uuid or submit_report(token, args.base_url, args.date_from, args.date_to)
    print(f"Report UUID: {uuid}", file=sys.stderr)

    status = wait_report(
        token,
        args.base_url,
        uuid,
        poll_interval=args.poll_interval,
        timeout_seconds=args.timeout,
    )

    link = status.get("link")
    if not isinstance(link, str) or not link:
        raise OzonApiError(f"Ready report does not contain download link: {status}")

    output_path = download_report(token, args.base_url, link, args.output)
    print(output_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OzonApiError, TimeoutError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
