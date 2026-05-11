"""Load Ozon external traffic analytics by UTM tags into a DataFrame."""

import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any

import pandas as pd
import sqlalchemy


API_BASE_URL = "https://api-performance.ozon.ru"
TOKEN_PATH = "/api/client/token"
REPORT_PATH = "/api/client/vendors/statistics"
REPORT_TYPE = "TRAFFIC_SOURCES"


class OzonApiError(RuntimeError):
    """Raised when Ozon Performance API returns an error response."""


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


class OzonUtmStatisticsClient:
    def __init__(self, client_id: str, client_secret: str, base_url: str = API_BASE_URL) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url
        self._token: str | None = None

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = self._get_access_token()
        return self._token

    def _get_access_token(self) -> str:
        response = request_json(
            "POST",
            f"{self.base_url}{TOKEN_PATH}",
            payload={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        token = response.get("access_token")
        if not isinstance(token, str) or not token:
            raise OzonApiError(f"Token response does not contain access_token: {response}")
        return token

    def _submit_report(self, date_from: str, date_to: str) -> str:
        response = request_json(
            "POST",
            f"{self.base_url}{REPORT_PATH}",
            token=self.token,
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

    def _get_report_status(self, uuid: str) -> dict[str, Any]:
        quoted_uuid = urllib.parse.quote(uuid, safe="")
        return request_json("GET", f"{self.base_url}{REPORT_PATH}/{quoted_uuid}", token=self.token)

    def _wait_report(
        self,
        uuid: str,
        *,
        poll_interval: int = 10,
        timeout_seconds: int = 1800,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds

        while True:
            status = self._get_report_status(uuid)
            state = str(status.get("state", "")).upper()

            if state in {"OK", "DONE", "SUCCESS", "COMPLETED"}:
                return status

            if state in {"ERROR", "FAILED", "FAIL"}:
                error = status.get("error") or status
                raise OzonApiError(f"Report generation failed: {error}")

            if time.monotonic() >= deadline:
                raise TimeoutError(f"Report {uuid} was not ready after {timeout_seconds} seconds")

            time.sleep(poll_interval)

    def _fetch_report_content(self, link: str, timeout: int = 120) -> bytes:
        url = urllib.parse.urljoin(f"{self.base_url}/", link)
        url_host = urllib.parse.urlparse(url).netloc
        api_host = urllib.parse.urlparse(self.base_url).netloc
        headers = {"Accept": "*/*"}
        if url_host == api_host:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(
            url,
            headers=headers,
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise OzonApiError(f"Report fetch failed: HTTP {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise OzonApiError(f"Report fetch failed: {error.reason}") from error

    def _report_content_to_dataframe(self, report: bytes) -> pd.DataFrame:
        if report.startswith(b"PK"):
            try:
                return pd.read_excel(io.BytesIO(report))
            except Exception:
                with zipfile.ZipFile(io.BytesIO(report)) as archive:
                    names = [name for name in archive.namelist() if not name.endswith("/")]
                    for name in names:
                        if name.lower().endswith((".csv", ".txt")):
                            data = archive.read(name)
                            try:
                                return pd.read_csv(io.BytesIO(data), sep=";", encoding="utf-8-sig")
                            except UnicodeDecodeError:
                                return pd.read_csv(io.BytesIO(data), sep=";", encoding="cp1251")
                    for name in names:
                        if name.lower().endswith((".xlsx", ".xlsm", ".xls")):
                            return pd.read_excel(io.BytesIO(archive.read(name)))

        try:
            return pd.read_csv(io.BytesIO(report), sep=";", encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(report), sep=";", encoding="cp1251")

    def get_utm_statistics(
        self,
        date_from: str,
        date_to: str,
        *,
        uuid: str | None = None,
        poll_interval: int = 10,
        timeout_seconds: int = 1800,
    ) -> pd.DataFrame:
        report_uuid = uuid or self._submit_report(date_from, date_to)
        status = self._wait_report(
            report_uuid,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
        )

        link = status.get("link")
        if not isinstance(link, str) or not link:
            raise OzonApiError(f"Ready report does not contain download link: {status}")

        report = self._fetch_report_content(link)
        return self._report_content_to_dataframe(report)


class to_postgresql():
    def __init__(self, port=None, host=None, user=None, password=None, database=None, schema=None):
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

    def sql_query(self, query=None):
        with self.engine.begin() as connection:
            connection.execute(sqlalchemy.text(query))

    def insert_into_table(self, table_name=None, data=None):
        data = data.copy()
        columns_sql = ", ".join(f'"{c}"' for c in data.columns.tolist())
        placeholders_sql = ", ".join(f":{c}" for c in data.columns.tolist())

        insert_sql = sqlalchemy.text(
            f'INSERT INTO {self.schema}."{table_name}" ({columns_sql}) VALUES ({placeholders_sql})'
        )

        rows = data.to_dict(orient="records")

        with self.engine.begin() as connection:
            connection.execute(insert_sql, rows)
