import logging
from typing import Any, Dict, List, Optional

from xero_python.accounting.models import Contact, CreditNote, CreditNotes, LineItem
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty, _to_float


class CreditNotesWriter(BaseWriter):
    """Writes CreditNote records to Xero.

    Supported CSV columns:
      CreditNoteID, CreditNoteNumber, Type, Status, Reference, CurrencyCode, CurrencyRate,
      DateString, FullyPaidOnDate, SentToContact, BrandingThemeID,
      Contact_ContactID, Contact_Name,
      LineItem_Description, LineItem_Quantity, LineItem_UnitAmount, LineItem_AccountCode,
      LineItem_TaxType, LineItem_ItemCode, LineItem_LineItemID
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: List[Dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} credit note(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        notes = [self._row_to_credit_note(row) for row in batch]
        notes_obj = CreditNotes(credit_notes=notes)
        try:
            if self.write_mode == "upsert":
                result = self.accounting_api.update_or_create_credit_notes(
                    self.tenant_id,
                    notes_obj,
                    summarize_errors=False,
                )
            else:
                result = self.accounting_api.create_credit_notes(
                    self.tenant_id,
                    notes_obj,
                    summarize_errors=False,
                )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write credit notes batch: {exc}")
            raise

    def _row_to_credit_note(self, row: Dict[str, Any]) -> CreditNote:
        note = CreditNote()

        if v := self._get(row, "CreditNoteID"):
            note.credit_note_id = v
        if v := self._get(row, "CreditNoteNumber"):
            note.credit_note_number = v
        if v := self._get(row, "Type"):
            note.type = v
        if v := self._get(row, "Status"):
            note.status = v
        if v := self._get(row, "Reference"):
            note.reference = v
        if v := self._get(row, "CurrencyCode"):
            note.currency_code = v
        if v := self._get(row, "DateString"):
            note.date_string = v
        if v := self._get(row, "BrandingThemeID"):
            note.branding_theme_id = v

        currency_rate = _to_float(row.get("CurrencyRate"))
        if currency_rate is not None:
            note.currency_rate = currency_rate

        contact = self._build_contact(row)
        if contact:
            note.contact = contact

        line_item = self._build_line_item(row)
        if line_item:
            note.line_items = [line_item]

        return note

    @staticmethod
    def _build_contact(row: Dict[str, Any]) -> Optional[Contact]:
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
    def _build_line_item(row: Dict[str, Any]) -> Optional[LineItem]:
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
        if hasattr(result, "credit_notes") and result.credit_notes:
            ok = sum(1 for cn in result.credit_notes if not cn.has_validation_errors)
            errors = [cn for cn in result.credit_notes if cn.has_validation_errors]
            logging.info(f"CreditNotes batch: {ok} ok, {len(errors)} with validation errors")
            for cn in errors:
                logging.warning(f"  CreditNote '{cn.credit_note_number}' validation errors: {cn.validation_errors}")
