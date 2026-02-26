import logging
from typing import Any, Dict, List, Optional

from xero_python.accounting.models import Account, Invoice, Payment, Payments
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty, _to_bool, _to_date, _to_float


class PaymentsWriter(BaseWriter):
    """Writes Payment records to Xero.

    Supported CSV columns:
      PaymentID, Date, Amount, Reference, CurrencyRate, IsReconciled, Status, PaymentType,
      Invoice_InvoiceID, Invoice_InvoiceNumber,
      Account_AccountID, Account_Code
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: List[Dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} payment(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        payments = [self._row_to_payment(row) for row in batch]
        payments_obj = Payments(payments=payments)
        try:
            # Xero API does not support updating payments; always create
            result = self.accounting_api.create_payments(
                self.tenant_id,
                payments_obj,
                summarize_errors=False,
            )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write payments batch: {exc}")
            raise

    def _row_to_payment(self, row: Dict[str, Any]) -> Payment:
        payment = Payment()

        if v := self._get(row, "PaymentID"):
            payment.payment_id = v
        if d := _to_date(row.get("Date")):
            payment.date = d
        if v := self._get(row, "Reference"):
            payment.reference = v
        if v := self._get(row, "Status"):
            payment.status = v
        if v := self._get(row, "PaymentType"):
            payment.payment_type = v

        amount = _to_float(row.get("Amount"))
        if amount is not None:
            payment.amount = amount

        currency_rate = _to_float(row.get("CurrencyRate"))
        if currency_rate is not None:
            payment.currency_rate = currency_rate

        is_reconciled = _to_bool(row.get("IsReconciled"))
        if is_reconciled is not None:
            payment.is_reconciled = is_reconciled

        invoice = self._build_invoice(row)
        if invoice:
            payment.invoice = invoice

        account = self._build_account(row)
        if account:
            payment.account = account

        return payment

    @staticmethod
    def _build_invoice(row: Dict[str, Any]) -> Optional[Invoice]:
        invoice_id = row.get("Invoice_InvoiceID")
        invoice_number = row.get("Invoice_InvoiceNumber")
        if _is_empty(invoice_id) and _is_empty(invoice_number):
            return None
        invoice = Invoice()
        if not _is_empty(invoice_id):
            invoice.invoice_id = str(invoice_id).strip()
        if not _is_empty(invoice_number):
            invoice.invoice_number = str(invoice_number).strip()
        return invoice

    @staticmethod
    def _build_account(row: Dict[str, Any]) -> Optional[Account]:
        account_id = row.get("Account_AccountID")
        account_code = row.get("Account_Code")
        if _is_empty(account_id) and _is_empty(account_code):
            return None
        account = Account()
        if not _is_empty(account_id):
            account.account_id = str(account_id).strip()
        if not _is_empty(account_code):
            account.code = str(account_code).strip()
        return account

    @staticmethod
    def _log_result(result) -> None:
        if hasattr(result, "payments") and result.payments:
            ok = sum(1 for p in result.payments if not p.validation_errors)
            errors = [p for p in result.payments if p.validation_errors]
            logging.info(f"Payments batch: {ok} ok, {len(errors)} with validation errors")
            for p in errors:
                logging.warning(f"  Payment '{p.payment_id}' validation errors: {p.validation_errors}")
