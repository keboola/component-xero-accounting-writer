import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date
from typing import Any

from xero_python.accounting import AccountingApi
from xero_python.api_client import ApiClient

BATCH_SIZE = 100


def _is_empty(value: Any) -> bool:
    """Return True if value should be treated as absent (None, empty string)."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_bool(value: Any) -> bool | None:
    """Convert a CSV string value to bool, or None if empty."""
    if _is_empty(value):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _to_float(value: Any) -> float | None:
    """Convert a CSV string value to float, or None if empty."""
    if _is_empty(value):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        logging.warning(f"Cannot convert '{value}' to float, skipping field")
        return None


def _to_date(value: Any) -> date | None:
    """Convert a CSV string (YYYY-MM-DD) to datetime.date, or None if empty/invalid."""
    if _is_empty(value):
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        logging.warning(f"Cannot convert '{value}' to date, skipping field")
        return None


def _to_int(value: Any) -> int | None:
    """Convert a CSV string value to int, or None if empty."""
    if _is_empty(value):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        logging.warning(f"Cannot convert '{value}' to int, skipping field")
        return None


class BaseWriter(ABC):
    """Abstract base class for all Xero entity writers."""

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        self.accounting_api = AccountingApi(api_client)
        self._raw_api_client = api_client
        self.tenant_id = tenant_id
        self.write_mode = write_mode

    @abstractmethod
    def write(self, rows: list[dict[str, Any]]) -> None:
        """Write rows to Xero. Must be implemented by subclasses."""
        pass

    def _process_in_batches(
        self,
        rows: list[dict[str, Any]],
        batch_fn: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        """Process rows in batches of BATCH_SIZE."""
        total = len(rows)
        for i in range(0, total, BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            end = min(i + BATCH_SIZE, total)
            logging.info(f"Processing batch {i // BATCH_SIZE + 1}: records {i + 1}-{end} of {total}")
            batch_fn(batch)

    @staticmethod
    def _get(row: dict[str, Any], key: str) -> str | None:
        """Get a string field from a CSV row, returning None if empty."""
        value = row.get(key)
        return None if _is_empty(value) else str(value).strip()
