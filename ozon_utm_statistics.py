#!/usr/bin/env python3
"""Load Ozon external traffic analytics by UTM tags into a DataFrame."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Any

import pandas as pd


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


@dataclass(frozen=True)
class ReportContent:
    data: bytes
    content_type: str
    filename: str
    url: str


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


def extract_filename(response: urllib.response.addinfourl, url: str) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    for chunk in disposition.split(";"):
        key, _, value = chunk.strip().partition("=")
        key = key.lower()
        if key == "filename*":
            _, _, encoded_filename = value.strip("\"'").partition("''")
            return urllib.parse.unquote(encoded_filename or value)
        if key == "filename":
            return value.strip("\"'")

    return urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]


def fetch_report_content(token: str, base_url: str, link: str, timeout: int = 120) -> ReportContent:
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
            return ReportContent(
                data=response.read(),
                content_type=response.headers.get("Content-Type", ""),
                filename=extract_filename(response, url),
                url=url,
            )
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise OzonApiError(f"Report fetch failed: HTTP {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise OzonApiError(f"Report fetch failed: {error.reason}") from error


def decode_csv_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise OzonApiError("Report CSV encoding is not supported")


def detect_csv_layout(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    candidates: list[tuple[int, str, int, str]] = []

    for index, line in enumerate(lines[:50]):
        counts = [(line.count(separator), separator) for separator in (";", ",", "\t")]
        count, separator = max(counts, key=lambda item: item[0])
        if count > 0:
            candidates.append((count, separator, index, line))

    if not candidates:
        return ",", 0

    max_count = max(count for count, _, _, _ in candidates)
    best_candidates = [candidate for candidate in candidates if candidate[0] == max_count]

    for _, separator, index, line in best_candidates:
        if not line.lstrip().startswith(separator):
            return separator, index

    _, separator, index, _ = best_candidates[0]
    return separator, index


def csv_bytes_to_dataframe(data: bytes) -> pd.DataFrame:
    text = decode_csv_text(data)
    separator, header_row = detect_csv_layout(text)
    dataframe = pd.read_csv(
        io.StringIO(text),
        sep=separator,
        skiprows=header_row,
        engine="python",
    )
    return dataframe.dropna(axis=1, how="all")


def zip_bytes_to_dataframe(data: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        for name in names:
            if name.lower().endswith((".csv", ".txt")):
                return csv_bytes_to_dataframe(archive.read(name))
        for name in names:
            if name.lower().endswith((".xlsx", ".xlsm", ".xls")):
                return pd.read_excel(io.BytesIO(archive.read(name)))

    raise OzonApiError("Report archive does not contain CSV or Excel files")


def report_content_to_dataframe(report: ReportContent) -> pd.DataFrame:
    filename = report.filename.lower()
    content_type = report.content_type.lower()

    if filename.endswith((".xlsx", ".xlsm", ".xls")) or "excel" in content_type or "spreadsheet" in content_type:
        return pd.read_excel(io.BytesIO(report.data))

    if zipfile.is_zipfile(io.BytesIO(report.data)):
        return zip_bytes_to_dataframe(report.data)

    return csv_bytes_to_dataframe(report.data)


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


class OzonUtmStatisticsClient:
    def __init__(self, credentials: OzonCredentials, base_url: str = API_BASE_URL) -> None:
        self.credentials = credentials
        self.base_url = base_url
        self._token: str | None = None

    @classmethod
    def from_env(cls, base_url: str = API_BASE_URL) -> "OzonUtmStatisticsClient":
        return cls(read_credentials(), base_url=base_url)

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = get_access_token(self.credentials, self.base_url)
        return self._token

    def submit_report(self, date_from: str, date_to: str) -> str:
        return submit_report(self.token, self.base_url, date_from, date_to)

    def get_report_status(self, uuid: str) -> dict[str, Any]:
        return get_report_status(self.token, self.base_url, uuid)

    def wait_report(
        self,
        uuid: str,
        *,
        poll_interval: int = 10,
        timeout_seconds: int = 1800,
    ) -> dict[str, Any]:
        return wait_report(
            self.token,
            self.base_url,
            uuid,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
        )

    def fetch_report_content(self, link: str) -> ReportContent:
        return fetch_report_content(self.token, self.base_url, link)

    def get_utm_statistics(
        self,
        date_from: str,
        date_to: str,
        *,
        uuid: str | None = None,
        poll_interval: int = 10,
        timeout_seconds: int = 1800,
    ) -> pd.DataFrame:
        report_uuid = uuid or self.submit_report(date_from, date_to)
        status = self.wait_report(
            report_uuid,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
        )

        link = status.get("link")
        if not isinstance(link, str) or not link:
            raise OzonApiError(f"Ready report does not contain download link: {status}")

        report = self.fetch_report_content(link)
        return report_content_to_dataframe(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Ozon UTM/external traffic analytics report and print it as a DataFrame.",
    )
    parser.add_argument("--date-from", required=True, help="Start date in YYYY-MM-DD format")
    parser.add_argument("--date-to", required=True, help="End date in YYYY-MM-DD format")
    parser.add_argument(
        "--uuid",
        help="Existing report UUID. If passed, the script skips report creation.",
    )
    parser.add_argument("--base-url", default=API_BASE_URL, help=f"API base URL. Default: {API_BASE_URL}")
    parser.add_argument("--poll-interval", default=10, type=int, help="Polling interval in seconds")
    parser.add_argument("--timeout", default=1800, type=int, help="Report generation timeout in seconds")
    parser.add_argument("--csv", action="store_true", help="Print full DataFrame as CSV instead of table preview")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    credentials = read_credentials()

    client = OzonUtmStatisticsClient(credentials, base_url=args.base_url)
    uuid = args.uuid or client.submit_report(args.date_from, args.date_to)
    print(f"Report UUID: {uuid}", file=sys.stderr)

    dataframe = client.get_utm_statistics(
        args.date_from,
        args.date_to,
        uuid=uuid,
        poll_interval=args.poll_interval,
        timeout_seconds=args.timeout,
    )

    if args.csv:
        print(dataframe.to_csv(index=False))
    else:
        print(dataframe)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OzonApiError, TimeoutError) as error:
        

class to_postgresql():
    def __init__(self,port=None,host=None,user=None,password=None,database=None,schema=None):
        self.schema=schema
        self.engine = sqlalchemy.create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}",
                pool_pre_ping=True,pool_recycle=1800,connect_args={"connect_timeout": 30},
                executemany_mode="values_plus_batch",executemany_batch_page_size=500)
        
    def create_table(self, table_name=None, data=None):
        column_name = ', '.join(f'"{d}" DATE' if d == 'date' or d == 'Дата' else f'"{d}" TEXT' for d in data.columns.tolist())
    
        with self.engine.begin() as connection:
            connection.execute(
                sqlalchemy.text(f'CREATE SCHEMA IF NOT EXISTS {self.schema}')
            )
            connection.execute(
                sqlalchemy.text(
                    f'CREATE TABLE IF NOT EXISTS {self.schema}."{table_name}" ({column_name})'
                )
            )
    
    def insert_into_table(self, table_name=None, data=None):
        data = data.copy()
        data['date'] = pd.to_datetime(data['date']).dt.date
        min_date = data['date'].min()
        max_date = data['date'].max()
    
        columns_sql = ", ".join(f'"{c}"' for c in data.columns.tolist())
        placeholders_sql = ", ".join(f":{c}" for c in data.columns.tolist())
    
        insert_sql = sqlalchemy.text(
            f'INSERT INTO {self.schema}."{table_name}" ({columns_sql}) VALUES ({placeholders_sql})'
        )
    
        delete_sql = sqlalchemy.text(
            f'DELETE FROM {self.schema}."{table_name}" WHERE "date" BETWEEN :min_date AND :max_date'
        )
    
        rows = data.to_dict(orient="records")
    
        with self.engine.begin() as connection:
            connection.execute(delete_sql, {
                "min_date": min_date,
                "max_date": max_date
            })
            connection.execute(insert_sql, rows)
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
