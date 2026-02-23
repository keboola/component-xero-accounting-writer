import logging
from typing import Any, Dict, List

from xero_python.accounting.models import Currency
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty


class CurrenciesWriter(BaseWriter):
    """Writes Currency records to Xero (PUT only — create or confirm).

    Supported CSV columns:
      Code, Description
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: List[Dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} currency/currencies to Xero")
        # Currencies endpoint only supports one at a time via create_currency
        for row in rows:
            self._write_single(row)

    def _write_single(self, row: Dict[str, Any]) -> None:
        currency = self._row_to_currency(row)
        if not currency.code:
            logging.warning("Skipping currency row with no Code")
            return
        try:
            result = self.accounting_api.create_currency(self.tenant_id, currency)
            if hasattr(result, "currencies") and result.currencies:
                logging.info(f"Currency '{currency.code}' written successfully")
            else:
                logging.info(f"Currency '{currency.code}' processed (may already exist)")
        except Exception as exc:
            logging.error(f"Failed to write currency '{currency.code}': {exc}")
            raise

    @staticmethod
    def _row_to_currency(row: Dict[str, Any]) -> Currency:
        currency = Currency()
        code = row.get("Code")
        if not _is_empty(code):
            currency.code = str(code).strip()
        description = row.get("Description")
        if not _is_empty(description):
            currency.description = str(description).strip()
        return currency
