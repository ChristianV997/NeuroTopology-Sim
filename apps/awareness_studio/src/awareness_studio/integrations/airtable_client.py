"""
Airtable REST API v0 client — stdlib urllib only, no extra dependencies.

Env vars (all optional):
  AIRTABLE_ENABLED=false     disable all mutation operations (default)
  AIRTABLE_API_KEY           Personal Access Token or legacy key
  AIRTABLE_BASE_ID           Base identifier (appXXXXXXXXXXXXXX)

Usage:
  from awareness_studio.integrations.airtable_client import AirtableClient
  client = AirtableClient(api_key="...", base_id="appXXX")
  records = client.list_records("Runs")
  rec = client.create_record("Runs", {"run_id": "x", "mode": "EXPLAIN"})
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.airtable.com/v0"
_TIMEOUT = 15
_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_PAGE_SIZE = 100


class AirtableError(Exception):
    """Raised on non-2xx Airtable responses."""
    def __init__(self, status: int, body: str, url: str) -> None:
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"Airtable HTTP {status} at {url}: {body[:300]}")


class AirtableClient:
    """
    Minimal Airtable v0 REST client.

    All write methods (create_record, update_record, upsert_by_field)
    check the enabled flag and raise if writes are not allowed.
    """

    def __init__(self, api_key: str, base_id: str, enabled: bool = False) -> None:
        if not api_key:
            raise ValueError("AIRTABLE_API_KEY is required")
        if not base_id:
            raise ValueError("AIRTABLE_BASE_ID is required")
        self._api_key = api_key
        self._base_id = base_id
        self._enabled = enabled

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_records(
        self,
        table: str,
        *,
        filter_formula: Optional[str] = None,
        fields: Optional[List[str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return all records from table (handles pagination automatically).

        filter_formula: Airtable formula string, e.g. "{run_id}='abc'"
        fields: restrict returned fields (list of field names)
        max_records: hard cap on number of records returned
        """
        records: List[Dict[str, Any]] = []
        offset: Optional[str] = None

        while True:
            params: Dict[str, Any] = {"pageSize": _PAGE_SIZE}
            if filter_formula:
                params["filterByFormula"] = filter_formula
            if fields:
                for i, f in enumerate(fields):
                    params[f"fields[{i}]"] = f
            if offset:
                params["offset"] = offset

            data = self._get(table, params=params)
            records.extend(data.get("records", []))
            offset = data.get("offset")

            if not offset:
                break
            if max_records and len(records) >= max_records:
                break

        return records[:max_records] if max_records else records

    def find_by_field(
        self, table: str, field: str, value: str
    ) -> Optional[Dict[str, Any]]:
        """Return first record where field equals value, or None."""
        safe_value = value.replace("'", "\\'")
        formula = f"{{{field}}}='{safe_value}'"
        records = self.list_records(table, filter_formula=formula, max_records=1)
        return records[0] if records else None

    # ── Write ─────────────────────────────────────────────────────────────────

    def create_record(self, table: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new record. Raises if not enabled."""
        self._assert_enabled("create_record")
        payload = {"fields": fields}
        return self._post(table, payload)

    def update_record(
        self, table: str, record_id: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Patch an existing record by its Airtable record ID."""
        self._assert_enabled("update_record")
        payload = {"fields": fields}
        return self._patch(table, record_id, payload)

    def upsert_by_field(
        self, table: str, key_field: str, key_value: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create or update based on key_field match.

        Returns the created or updated record.
        Includes key_field in fields automatically.
        """
        self._assert_enabled("upsert_by_field")
        existing = self.find_by_field(table, key_field, key_value)
        merged = {key_field: key_value, **fields}
        if existing:
            record_id = existing["id"]
            logger.debug("[airtable] updating %s record %s", table, record_id)
            return self.update_record(table, record_id, merged)
        logger.debug("[airtable] creating new %s record for %s=%s", table, key_field, key_value)
        return self.create_record(table, merged)

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _url(self, table: str, suffix: str = "") -> str:
        encoded = urllib.parse.quote(table, safe="")
        return f"{_BASE_URL}/{self._base_id}/{encoded}{suffix}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _get(self, table: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._url(table)
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return self._request("GET", url, body=None)

    def _post(self, table: str, payload: Any) -> Any:
        url = self._url(table)
        return self._request("POST", url, body=payload)

    def _patch(self, table: str, record_id: str, payload: Any) -> Any:
        url = self._url(table, f"/{record_id}")
        return self._request("PATCH", url, body=payload)

    def _request(self, method: str, url: str, body: Any) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(1, _MAX_RETRIES + 1):
            req = urllib.request.Request(
                url, data=data, headers=self._headers(), method=method
            )
            try:
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                status = exc.code
                body_bytes = exc.read()
                body_str = body_bytes.decode(errors="replace")
                if status in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(
                        "[airtable] HTTP %s at %s — retry %d/%d in %ds",
                        status, url, attempt, _MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue
                raise AirtableError(status, body_str, url) from exc
        raise AirtableError(0, "Max retries exceeded", url)

    def _assert_enabled(self, op: str) -> None:
        if not self._enabled:
            raise PermissionError(
                f"Airtable write '{op}' blocked: AIRTABLE_ENABLED=false. "
                "Set AIRTABLE_ENABLED=true to allow writes."
            )
