import logging
from typing import Any, Dict, List, Optional

from xero_python.accounting.models import Account, BankTransaction, BankTransactions, Contact, CurrencyCode, LineItem
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty, _to_bool, _to_float


class BankTransactionsWriter(BaseWriter):
    """Writes BankTransaction (spend/receive money) records to Xero.

    Supported CSV columns:
      BankTransactionID, Type, Status, Reference, CurrencyCode, CurrencyRate,
      Url, IsReconciled, DateString,
      Contact_ContactID, Contact_Name,
      BankAccount_AccountID, BankAccount_Code,
      LineItem_Description, LineItem_Quantity, LineItem_UnitAmount, LineItem_AccountCode,
      LineItem_TaxType, LineItem_ItemCode, LineItem_LineItemID
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: List[Dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} bank transaction(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        txns = [self._row_to_bank_transaction(row) for row in batch]
        txns_obj = BankTransactions(bank_transactions=txns)
        try:
            if self.write_mode == "upsert":
                result = self.accounting_api.update_or_create_bank_transactions(
                    self.tenant_id,
                    txns_obj,
                    summarize_errors=False,
                )
            else:
                result = self.accounting_api.create_bank_transactions(
                    self.tenant_id,
                    txns_obj,
                    summarize_errors=False,
                )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write bank transactions batch: {exc}")
            raise

    def _row_to_bank_transaction(self, row: Dict[str, Any]) -> BankTransaction:
        # BankTransaction constructor requires type, line_items, bank_account to be non-None
        txn_type = self._get(row, "Type")
        bank_account = self._build_bank_account(row) or Account()
        line_item = self._build_line_item(row)
        line_items = [line_item] if line_item else []

        txn = BankTransaction(type=txn_type, line_items=line_items, bank_account=bank_account)

        if v := self._get(row, "BankTransactionID"):
            txn.bank_transaction_id = v
        if v := self._get(row, "Status"):
            txn.status = v
        if v := self._get(row, "Reference"):
            txn.reference = v
        if v := self._get(row, "CurrencyCode"):
            txn.currency_code = CurrencyCode(v)
        if v := self._get(row, "Url"):
            txn.url = v
        if v := self._get(row, "DateString"):
            txn.date_string = v

        currency_rate = _to_float(row.get("CurrencyRate"))
        if currency_rate is not None:
            txn.currency_rate = currency_rate

        is_reconciled = _to_bool(row.get("IsReconciled"))
        if is_reconciled is not None:
            txn.is_reconciled = is_reconciled

        contact = self._build_contact(row)
        if contact:
            txn.contact = contact

        return txn

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
    def _build_bank_account(row: Dict[str, Any]) -> Optional[Account]:
        account_id = row.get("BankAccount_AccountID")
        account_code = row.get("BankAccount_Code")
        if _is_empty(account_id) and _is_empty(account_code):
            return None
        account = Account()
        if not _is_empty(account_id):
            account.account_id = str(account_id).strip()
        if not _is_empty(account_code):
            account.code = str(account_code).strip()
        return account

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
        if hasattr(result, "bank_transactions") and result.bank_transactions:
            ok = sum(1 for t in result.bank_transactions if not t.validation_errors)
            errors = [t for t in result.bank_transactions if t.validation_errors]
            logging.info(f"BankTransactions batch: {ok} ok, {len(errors)} with validation errors")
            for t in errors:
                logging.warning(f"  BankTransaction '{t.bank_transaction_id}' validation errors: {t.validation_errors}")
