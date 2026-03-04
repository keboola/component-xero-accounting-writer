import logging
from typing import Any

from keboola.component.exceptions import UserException
from xero_python.accounting.models import Contact, CurrencyCode, LineItem, Quote, Quotes, QuoteStatusCodes
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty, _to_float


class QuotesWriter(BaseWriter):
    """Writes Quote records to Xero.

    Supported CSV columns:
      QuoteID, QuoteNumber, Reference, CurrencyCode, CurrencyRate, Status,
      Title, Summary, Terms, DateString, ExpiryDateString,
      Contact_ContactID, Contact_Name,
      LineItem_Description, LineItem_Quantity, LineItem_UnitAmount, LineItem_AccountCode,
      LineItem_TaxType, LineItem_ItemCode, LineItem_LineItemID
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: list[dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} quote(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        quotes = [self._row_to_quote(row) for row in batch]
        quotes_obj = Quotes(quotes=quotes)
        try:
            if self.write_mode == "upsert":
                result = self.accounting_api.update_or_create_quotes(
                    self.tenant_id,
                    quotes_obj,
                    summarize_errors=False,
                )
            else:
                result = self.accounting_api.create_quotes(
                    self.tenant_id,
                    quotes_obj,
                    summarize_errors=False,
                )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write quotes batch: {exc}")
            raise UserException(f"Failed to write quotes batch: {exc}") from exc

    def _row_to_quote(self, row: dict[str, Any]) -> Quote:
        quote = Quote()

        if v := self._get(row, "QuoteID"):
            quote.quote_id = v
        if v := self._get(row, "QuoteNumber"):
            quote.quote_number = v
        if v := self._get(row, "Reference"):
            quote.reference = v
        if v := self._get(row, "CurrencyCode"):
            quote.currency_code = CurrencyCode(v)
        if v := self._get(row, "Status"):
            quote.status = QuoteStatusCodes(v)
        if v := self._get(row, "Title"):
            quote.title = v
        if v := self._get(row, "Summary"):
            quote.summary = v
        if v := self._get(row, "Terms"):
            quote.terms = v
        if v := self._get(row, "DateString"):
            quote.date_string = v
        if v := self._get(row, "ExpiryDateString"):
            quote.expiry_date_string = v

        currency_rate = _to_float(row.get("CurrencyRate"))
        if currency_rate is not None:
            quote.currency_rate = currency_rate

        contact = self._build_contact(row)
        if contact:
            quote.contact = contact

        line_item = self._build_line_item(row)
        if line_item:
            quote.line_items = [line_item]

        return quote

    @staticmethod
    def _build_contact(row: dict[str, Any]) -> Contact | None:
        contact_id = row.get("Contact_ContactID")
        contact_name = row.get("Contact_Name")
        if _is_empty(contact_id) and _is_empty(contact_name):
            return None
        contact = Contact()
        if not _is_empty(contact_id):
            contact.contact_id = str(contact_id).strip()
        if not _is_empty(contact_name):
            contact.name = str(contact_name).strip()
        return contact

    @staticmethod
    def _build_line_item(row: dict[str, Any]) -> LineItem | None:
        description = row.get("LineItem_Description")
        if _is_empty(description):
            return None
        line_item = LineItem(description=str(description).strip())
        if v := row.get("LineItem_Quantity"):
            q = _to_float(v)
            if q is not None:
                line_item.quantity = q
        if v := row.get("LineItem_UnitAmount"):
            a = _to_float(v)
            if a is not None:
                line_item.unit_amount = a
        if v := row.get("LineItem_AccountCode"):
            if not _is_empty(v):
                line_item.account_code = str(v).strip()
        if v := row.get("LineItem_TaxType"):
            if not _is_empty(v):
                line_item.tax_type = str(v).strip()
        if v := row.get("LineItem_ItemCode"):
            if not _is_empty(v):
                line_item.item_code = str(v).strip()
        return line_item

    @staticmethod
    def _log_result(result) -> None:
        if hasattr(result, "quotes") and result.quotes:
            ok = sum(1 for q in result.quotes if not q.validation_errors)
            errors = [q for q in result.quotes if q.validation_errors]
            logging.info(f"Quotes batch: {ok} ok, {len(errors)} with validation errors")
            for q in errors:
                logging.warning(f"  Quote '{q.quote_number}' validation errors: {q.validation_errors}")
