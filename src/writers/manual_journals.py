import logging
from typing import Any

from keboola.component.exceptions import UserException
from xero_python.accounting.models import ManualJournal, ManualJournalLine, ManualJournals
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty, _to_bool, _to_float


class ManualJournalsWriter(BaseWriter):
    """Writes ManualJournal records to Xero.

    Supported CSV columns:
      ManualJournalID, Narration, DateString, Status, Url, ShowOnCashBasisReports,
      HasAttachments, HasValidationErrors,
      JournalLine_Description, JournalLine_LineAmount, JournalLine_AccountCode,
      JournalLine_TaxType, JournalLine_TaxAmount, JournalLine_IsBlank
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: list[dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} manual journal(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        journals = [self._row_to_journal(row) for row in batch]
        journals_obj = ManualJournals(manual_journals=journals)
        try:
            if self.write_mode == "upsert":
                result = self.accounting_api.update_or_create_manual_journals(
                    self.tenant_id,
                    journals_obj,
                    summarize_errors=False,
                )
            else:
                result = self.accounting_api.create_manual_journals(
                    self.tenant_id,
                    journals_obj,
                    summarize_errors=False,
                )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write manual journals batch: {exc}")
            raise UserException(f"Failed to write manual journals batch: {exc}") from exc

    def _row_to_journal(self, row: dict[str, Any]) -> ManualJournal:
        narration = self._get(row, "Narration") or ""
        journal = ManualJournal(narration=narration)

        if v := self._get(row, "ManualJournalID"):
            journal.manual_journal_id = v
        if v := self._get(row, "DateString"):
            journal.date_string = v
        if v := self._get(row, "Status"):
            journal.status = v
        if v := self._get(row, "Url"):
            journal.url = v

        show_on_cash = _to_bool(row.get("ShowOnCashBasisReports"))
        if show_on_cash is not None:
            journal.show_on_cash_basis_reports = show_on_cash

        journal_line = self._build_journal_line(row)
        if journal_line:
            journal.journal_lines = [journal_line]

        return journal

    @staticmethod
    def _build_journal_line(row: dict[str, Any]):
        description = row.get("JournalLine_Description")
        line_amount = _to_float(row.get("JournalLine_LineAmount"))
        if _is_empty(description) and line_amount is None:
            return None
        line = ManualJournalLine()
        if not _is_empty(description):
            line.description = str(description).strip()
        if line_amount is not None:
            line.line_amount = line_amount
        if v := row.get("JournalLine_AccountCode"):
            if not _is_empty(v):
                line.account_code = str(v).strip()
        if v := row.get("JournalLine_TaxType"):
            if not _is_empty(v):
                line.tax_type = str(v).strip()
        return line

    @staticmethod
    def _log_result(result) -> None:
        if hasattr(result, "manual_journals") and result.manual_journals:
            ok = sum(1 for j in result.manual_journals if not j.validation_errors)
            errors = [j for j in result.manual_journals if j.validation_errors]
            logging.info(f"ManualJournals batch: {ok} ok, {len(errors)} with validation errors")
            for j in errors:
                logging.warning(f"  Journal '{j.narration}' validation errors: {j.validation_errors}")
