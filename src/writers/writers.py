"""Data-driven Xero entity writers.

Replaces the per-entity writer files with a single GenericWriter driven by
EntityConfig descriptors. Special-case entities (Currencies, TrackingCategories)
that can't use batch endpoints retain their own small classes.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from keboola.component.exceptions import UserException
from xero_python.accounting import AccountingApi
from xero_python.accounting.models import (
    Account,
    Address,
    BankTransaction,
    BankTransactions,
    Contact,
    Contacts,
    CreditNote,
    CreditNotes,
    Currency,
    CurrencyCode,
    Employee,
    Employees,
    Invoice,
    Invoices,
    Item,
    Items,
    LineItem,
    ManualJournal,
    ManualJournalLine,
    ManualJournals,
    Payment,
    Payments,
    Phone,
    Purchase,
    PurchaseOrder,
    PurchaseOrders,
    Quote,
    Quotes,
    QuoteStatusCodes,
    TrackingCategory,
)
from xero_python.api_client import ApiClient
from xero_python.exceptions import ApiException

from configuration import EntityType

# ------------------------------------------------------------------ #
# Helpers (formerly base_writer.py)                                    #
# ------------------------------------------------------------------ #

BATCH_SIZE = 100


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_bool(value: Any) -> bool | None:
    if _is_empty(value):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _to_float(value: Any) -> float | None:
    if _is_empty(value):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        logging.warning(f"Cannot convert '{value}' to float, skipping field")
        return None


def _to_date(value: Any) -> date | None:
    if _is_empty(value):
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        logging.warning(f"Cannot convert '{value}' to date, skipping field")
        return None


def _get(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return None if _is_empty(value) else str(value).strip()


class BaseWriter(ABC):
    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        self.accounting_api = AccountingApi(api_client)
        self.tenant_id = tenant_id
        self.write_mode = write_mode
        self.collected_errors: list[dict] = []

    @staticmethod
    def _extract_error_messages(validation_errors) -> str:
        msgs = []
        for ve in validation_errors or []:
            if isinstance(ve, dict):
                msgs.append(ve.get("message", str(ve)))
            else:
                msgs.append(str(ve))
        return "; ".join(msgs)

    @abstractmethod
    def write(self, rows: list[dict[str, Any]]) -> None: ...

    def _process_in_batches(
        self,
        rows: list[dict[str, Any]],
        batch_fn: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        total = len(rows)
        for i in range(0, total, BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            end = min(i + BATCH_SIZE, total)
            logging.info(f"Processing batch {i // BATCH_SIZE + 1}: records {i + 1}-{end} of {total}")
            batch_fn(batch)


# ------------------------------------------------------------------ #
# Shared sub-object builders                                           #
# ------------------------------------------------------------------ #


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
    if v := row.get("LineItem_DiscountRate"):
        d = _to_float(v)
        if d is not None:
            line_item.discount_rate = d
    if v := row.get("LineItem_LineItemID"):
        if not _is_empty(v):
            line_item.line_item_id = str(v).strip()
    return line_item


def _build_phone(row: dict[str, Any]) -> Phone | None:
    phone_number = row.get("Phone_PhoneNumber")
    if _is_empty(phone_number):
        return None
    phone = Phone(phone_number=str(phone_number).strip())
    for col, attr in [
        ("Phone_PhoneType", "phone_type"),
        ("Phone_PhoneAreaCode", "phone_area_code"),
        ("Phone_PhoneCountryCode", "phone_country_code"),
    ]:
        v = row.get(col)
        if not _is_empty(v):
            setattr(phone, attr, str(v).strip())
    return phone


def _build_address(row: dict[str, Any]) -> Address | None:
    has_address = any(
        not _is_empty(row.get(k))
        for k in ("Address_AddressLine1", "Address_City", "Address_PostalCode", "Address_Country")
    )
    if not has_address:
        return None
    address = Address()
    if v := row.get("Address_AddressType"):
        if not _is_empty(v):
            address.address_type = str(v).strip()
    for col, attr in [
        ("Address_AddressLine1", "address_line1"),
        ("Address_AddressLine2", "address_line2"),
        ("Address_AddressLine3", "address_line3"),
        ("Address_AddressLine4", "address_line4"),
        ("Address_City", "city"),
        ("Address_Region", "region"),
        ("Address_PostalCode", "postal_code"),
        ("Address_Country", "country"),
        ("Address_AttentionTo", "attention_to"),
    ]:
        v = row.get(col)
        if not _is_empty(v):
            setattr(address, attr, str(v).strip())
    return address


# ------------------------------------------------------------------ #
# Row converters (one per entity type)                                 #
# ------------------------------------------------------------------ #


def _row_to_contact(row: dict[str, Any]) -> Contact:
    contact = Contact()
    for col, attr in [
        ("ContactID", "contact_id"),
        ("ContactNumber", "contact_number"),
        ("AccountNumber", "account_number"),
        ("ContactStatus", "contact_status"),
        ("Name", "name"),
        ("FirstName", "first_name"),
        ("LastName", "last_name"),
        ("EmailAddress", "email_address"),
        ("BankAccountDetails", "bank_account_details"),
        ("TaxNumber", "tax_number"),
        ("AccountsReceivableTaxType", "accounts_receivable_tax_type"),
        ("AccountsPayableTaxType", "accounts_payable_tax_type"),
        ("Website", "website"),
    ]:
        if v := _get(row, col):
            setattr(contact, attr, v)
    if v := _get(row, "DefaultCurrency"):
        contact.default_currency = CurrencyCode(v)
    if (b := _to_bool(row.get("IsSupplier"))) is not None:
        contact.is_supplier = b
    if (b := _to_bool(row.get("IsCustomer"))) is not None:
        contact.is_customer = b
    if phone := _build_phone(row):
        contact.phones = [phone]
    if address := _build_address(row):
        contact.addresses = [address]
    return contact


def _row_to_invoice(row: dict[str, Any]) -> Invoice:
    invoice = Invoice()
    for col, attr in [
        ("InvoiceID", "invoice_id"),
        ("InvoiceNumber", "invoice_number"),
        ("Type", "type"),
        ("Status", "status"),
        ("Reference", "reference"),
        ("Url", "url"),
        ("DateString", "date_string"),
        ("DueDateString", "due_date_string"),
        ("BrandingThemeID", "branding_theme_id"),
    ]:
        if v := _get(row, col):
            setattr(invoice, attr, v)
    if v := _get(row, "CurrencyCode"):
        invoice.currency_code = CurrencyCode(v)
    if (r := _to_float(row.get("CurrencyRate"))) is not None:
        invoice.currency_rate = r
    if contact := _build_contact(row):
        invoice.contact = contact
    if li := _build_line_item(row):
        invoice.line_items = [li]
    return invoice


def _row_to_payment(row: dict[str, Any]) -> Payment:
    payment = Payment()
    for col, attr in [
        ("PaymentID", "payment_id"),
        ("Reference", "reference"),
        ("Status", "status"),
        ("PaymentType", "payment_type"),
    ]:
        if v := _get(row, col):
            setattr(payment, attr, v)
    if d := _to_date(row.get("Date")):
        payment.date = d
    if (a := _to_float(row.get("Amount"))) is not None:
        payment.amount = a
    if (r := _to_float(row.get("CurrencyRate"))) is not None:
        payment.currency_rate = r
    if (b := _to_bool(row.get("IsReconciled"))) is not None:
        payment.is_reconciled = b
    inv_id = row.get("Invoice_InvoiceID")
    inv_num = row.get("Invoice_InvoiceNumber")
    if not (_is_empty(inv_id) and _is_empty(inv_num)):
        inv = Invoice()
        if not _is_empty(inv_id):
            inv.invoice_id = str(inv_id).strip()
        if not _is_empty(inv_num):
            inv.invoice_number = str(inv_num).strip()
        payment.invoice = inv
    acc_id = row.get("Account_AccountID")
    acc_code = row.get("Account_Code")
    if not (_is_empty(acc_id) and _is_empty(acc_code)):
        acc = Account()
        if not _is_empty(acc_id):
            acc.account_id = str(acc_id).strip()
        if not _is_empty(acc_code):
            acc.code = str(acc_code).strip()
        payment.account = acc
    return payment


def _row_to_purchase_order(row: dict[str, Any]) -> PurchaseOrder:
    po = PurchaseOrder()
    for col, attr in [
        ("PurchaseOrderID", "purchase_order_id"),
        ("PurchaseOrderNumber", "purchase_order_number"),
        ("DateString", "date_string"),
        ("DeliveryDateString", "delivery_date_string"),
        ("Status", "status"),
        ("Reference", "reference"),
        ("DeliveryAddress", "delivery_address"),
        ("AttentionTo", "attention_to"),
        ("Telephone", "telephone"),
        ("DeliveryInstructions", "delivery_instructions"),
    ]:
        if v := _get(row, col):
            setattr(po, attr, v)
    if v := _get(row, "CurrencyCode"):
        po.currency_code = CurrencyCode(v)
    if (r := _to_float(row.get("CurrencyRate"))) is not None:
        po.currency_rate = r
    if contact := _build_contact(row):
        po.contact = contact
    if li := _build_line_item(row):
        po.line_items = [li]
    return po


def _row_to_manual_journal(row: dict[str, Any]) -> ManualJournal:
    narration = _get(row, "Narration")
    if not narration:
        raise UserException(f"Row is missing required field 'Narration': {row}")
    journal = ManualJournal(narration=narration)
    for col, attr in [
        ("ManualJournalID", "manual_journal_id"),
        ("DateString", "date_string"),
        ("Status", "status"),
        ("Url", "url"),
    ]:
        if v := _get(row, col):
            setattr(journal, attr, v)
    if (b := _to_bool(row.get("ShowOnCashBasisReports"))) is not None:
        journal.show_on_cash_basis_reports = b
    description = row.get("JournalLine_Description")
    line_amount = _to_float(row.get("JournalLine_LineAmount"))
    if not (_is_empty(description) and line_amount is None):
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
        journal.journal_lines = [line]
    return journal


def _row_to_item(row: dict[str, Any]) -> Item:
    code = _get(row, "Code")
    if not code:
        raise UserException(f"Row is missing required field 'Code': {row}")
    item = Item(code=code)
    for col, attr in [
        ("ItemID", "item_id"),
        ("Name", "name"),
        ("Description", "description"),
        ("PurchaseDescription", "purchase_description"),
    ]:
        if v := _get(row, col):
            setattr(item, attr, v)
    if (b := _to_bool(row.get("IsSold"))) is not None:
        item.is_sold = b
    if (b := _to_bool(row.get("IsPurchased"))) is not None:
        item.is_purchased = b
    purchase_price = _to_float(row.get("PurchaseDetails_UnitPrice"))
    purchase_code = row.get("PurchaseDetails_AccountCode")
    if purchase_price is not None or not _is_empty(purchase_code):
        pd = Purchase()
        if purchase_price is not None:
            pd.unit_price = purchase_price
        if not _is_empty(purchase_code):
            pd.account_code = str(purchase_code).strip()
        if v := row.get("PurchaseDetails_TaxType"):
            if not _is_empty(v):
                pd.tax_type = str(v).strip()
        item.purchase_details = pd
    # xero_python uses Purchase model for sales_details too
    sales_price = _to_float(row.get("SalesDetails_UnitPrice"))
    sales_code = row.get("SalesDetails_AccountCode")
    if sales_price is not None or not _is_empty(sales_code):
        sd = Purchase()
        if sales_price is not None:
            sd.unit_price = sales_price
        if not _is_empty(sales_code):
            sd.account_code = str(sales_code).strip()
        if v := row.get("SalesDetails_TaxType"):
            if not _is_empty(v):
                sd.tax_type = str(v).strip()
        item.sales_details = sd
    return item


def _row_to_credit_note(row: dict[str, Any]) -> CreditNote:
    note = CreditNote()
    for col, attr in [
        ("CreditNoteID", "credit_note_id"),
        ("CreditNoteNumber", "credit_note_number"),
        ("Type", "type"),
        ("Status", "status"),
        ("Reference", "reference"),
        ("DateString", "date_string"),
        ("BrandingThemeID", "branding_theme_id"),
    ]:
        if v := _get(row, col):
            setattr(note, attr, v)
    if v := _get(row, "CurrencyCode"):
        note.currency_code = CurrencyCode(v)
    if (r := _to_float(row.get("CurrencyRate"))) is not None:
        note.currency_rate = r
    if contact := _build_contact(row):
        note.contact = contact
    if li := _build_line_item(row):
        note.line_items = [li]
    return note


def _row_to_employee(row: dict[str, Any]) -> Employee:
    employee = Employee()
    for col, attr in [
        ("EmployeeID", "employee_id"),
        ("FirstName", "first_name"),
        ("LastName", "last_name"),
        ("Status", "status"),
    ]:
        if v := _get(row, col):
            setattr(employee, attr, v)
    return employee


def _row_to_quote(row: dict[str, Any]) -> Quote:
    quote = Quote()
    for col, attr in [
        ("QuoteID", "quote_id"),
        ("QuoteNumber", "quote_number"),
        ("Reference", "reference"),
        ("Title", "title"),
        ("Summary", "summary"),
        ("Terms", "terms"),
        ("DateString", "date_string"),
        ("ExpiryDateString", "expiry_date_string"),
    ]:
        if v := _get(row, col):
            setattr(quote, attr, v)
    if v := _get(row, "CurrencyCode"):
        quote.currency_code = CurrencyCode(v)
    if v := _get(row, "Status"):
        quote.status = QuoteStatusCodes(v)
    if (r := _to_float(row.get("CurrencyRate"))) is not None:
        quote.currency_rate = r
    if contact := _build_contact(row):
        quote.contact = contact
    if li := _build_line_item(row):
        quote.line_items = [li]
    return quote


def _row_to_bank_transaction(row: dict[str, Any]) -> BankTransaction:
    txn_type = _get(row, "Type")
    ba_id = row.get("BankAccount_AccountID")
    ba_code = row.get("BankAccount_Code")
    bank_account = Account()
    if not (_is_empty(ba_id) and _is_empty(ba_code)):
        if not _is_empty(ba_id):
            bank_account.account_id = str(ba_id).strip()
        if not _is_empty(ba_code):
            bank_account.code = str(ba_code).strip()
    li = _build_line_item(row)
    txn = BankTransaction(type=txn_type, line_items=[li] if li else [], bank_account=bank_account)
    for col, attr in [
        ("BankTransactionID", "bank_transaction_id"),
        ("Status", "status"),
        ("Reference", "reference"),
        ("Url", "url"),
        ("DateString", "date_string"),
    ]:
        if v := _get(row, col):
            setattr(txn, attr, v)
    if v := _get(row, "CurrencyCode"):
        txn.currency_code = CurrencyCode(v)
    if (r := _to_float(row.get("CurrencyRate"))) is not None:
        txn.currency_rate = r
    if (b := _to_bool(row.get("IsReconciled"))) is not None:
        txn.is_reconciled = b
    if contact := _build_contact(row):
        txn.contact = contact
    return txn


# ------------------------------------------------------------------ #
# Entity config + Generic writer                                        #
# ------------------------------------------------------------------ #


@dataclass
class EntityConfig:
    entity_name: str
    row_to_model: Callable
    collection_class: type
    collection_kwarg: str
    result_attr: str
    result_id_attr: str
    create_method: str
    upsert_method: str | None = None
    upsert_summarize: bool = True  # whether to pass summarize_errors=False to upsert call
    collect_errors: bool = True  # whether to collect validation errors from the result


class GenericWriter(BaseWriter):
    """Data-driven batch writer for standard Xero entities."""

    def __init__(self, config: EntityConfig, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)
        self.config = config

    def write(self, rows: list[dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} {self.config.entity_name.lower()} to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        models = [self.config.row_to_model(row) for row in batch]
        collection = self.config.collection_class(**{self.config.collection_kwarg: models})
        try:
            if self.write_mode == "upsert" and self.config.upsert_method:
                method = getattr(self.accounting_api, self.config.upsert_method)
                kwargs = {"summarize_errors": False} if self.config.upsert_summarize else {}
                result = method(self.tenant_id, collection, **kwargs)
            else:
                method = getattr(self.accounting_api, self.config.create_method)
                result = method(self.tenant_id, collection, summarize_errors=False)
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write {self.config.entity_name.lower()} batch: {exc}")
            raise UserException(f"Failed to write {self.config.entity_name.lower()} batch: {exc}") from exc

    def _log_result(self, result) -> None:
        items = getattr(result, self.config.result_attr, None) or []
        if not self.config.collect_errors:
            logging.info(f"{self.config.entity_name} batch: {len(items)} processed")
            return
        ok = sum(1 for item in items if not getattr(item, "validation_errors", None))
        errors = [item for item in items if getattr(item, "validation_errors", None)]
        logging.info(f"{self.config.entity_name} batch: {ok} ok, {len(errors)} with validation errors")
        for item in errors:
            record_id = str(getattr(item, self.config.result_id_attr, "") or "")
            logging.warning(f"  {self.config.entity_name} '{record_id}' validation errors: {item.validation_errors}")
            self.collected_errors.append(
                {
                    "entity_type": self.config.entity_name,
                    "record_id": record_id,
                    "errors": self._extract_error_messages(item.validation_errors),
                }
            )


# ------------------------------------------------------------------ #
# Special-case writers (non-batch endpoints)                           #
# ------------------------------------------------------------------ #


class CurrenciesWriter(BaseWriter):
    """Writes Currency records one at a time (no batch endpoint)."""

    def write(self, rows: list[dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} currency/currencies to Xero")
        for row in rows:
            self._write_single(row)

    def _write_single(self, row: dict[str, Any]) -> None:
        currency = Currency()
        if code := _get(row, "Code"):
            currency.code = CurrencyCode(code)
        if description := _get(row, "Description"):
            currency.description = description
        if not currency.code:
            logging.warning("Skipping currency row with no Code")
            return
        try:
            result = self.accounting_api.create_currency(self.tenant_id, currency)
            if hasattr(result, "currencies") and result.currencies:
                logging.info(f"Currency '{currency.code}' written successfully")
            else:
                logging.info(f"Currency '{currency.code}' processed (may already exist)")
        except ApiException as exc:
            if exc.status == 400 and "already subscribed" in str(exc.body).lower():
                logging.warning(f"Currency '{currency.code}' already exists in Xero, skipping")
            else:
                logging.error(f"Failed to write currency '{currency.code}': {exc}")
                raise


class TrackingCategoriesWriter(BaseWriter):
    """Writes TrackingCategory records one at a time (no batch endpoint)."""

    def write(self, rows: list[dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} tracking category/categories to Xero (mode={self.write_mode})")
        for row in rows:
            self._write_single(row)

    def _write_single(self, row: dict[str, Any]) -> None:
        category = TrackingCategory()
        if v := _get(row, "TrackingCategoryID"):
            category.tracking_category_id = v
        if v := _get(row, "Name"):
            category.name = v
        if v := _get(row, "Status"):
            category.status = v
        if not category.name:
            logging.warning("Skipping tracking category row with no Name")
            return
        try:
            if self.write_mode == "upsert" and category.tracking_category_id:
                self.accounting_api.update_tracking_category(self.tenant_id, category.tracking_category_id, category)
                logging.info(f"Updated tracking category '{category.name}'")
            else:
                self.accounting_api.create_tracking_category(self.tenant_id, category)
                logging.info(f"Created tracking category '{category.name}'")
        except ApiException as exc:
            if exc.status == 400 and "unique category name" in str(exc.body).lower():
                logging.warning(f"Tracking category '{category.name}' already exists in Xero, skipping")
            else:
                raise UserException(f"Failed to write tracking category '{category.name}': {exc}") from exc


# ------------------------------------------------------------------ #
# Entity metadata (field suggestions + required sets for sync actions) #
# ------------------------------------------------------------------ #

# Required and commonly-used fields per entity. Used by the loadFieldSuggestions
# sync action to pre-fill column_mapping. Fields are ordered: required first.
ENTITY_FIELD_SUGGESTIONS: dict[str, list[str]] = {
    "Contacts": [
        "Name",
        "FirstName",
        "LastName",
        "EmailAddress",
        "IsSupplier",
        "IsCustomer",
        "DefaultCurrency",
        "ContactNumber",
        "AccountNumber",
        "TaxNumber",
        "Phone_PhoneType",
        "Phone_PhoneNumber",
        "Phone_PhoneAreaCode",
        "Phone_PhoneCountryCode",
        "Address_AddressType",
        "Address_AddressLine1",
        "Address_City",
        "Address_Region",
        "Address_PostalCode",
        "Address_Country",
    ],
    "Invoices": [
        "Type",
        "Status",
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_Quantity",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
        "InvoiceID",
        "InvoiceNumber",
        "Reference",
        "CurrencyCode",
        "DateString",
        "DueDateString",
        "LineItem_TaxType",
        "LineItem_ItemCode",
    ],
    "Payments": [
        "Amount",
        "Date",
        "Invoice_InvoiceID",
        "Invoice_InvoiceNumber",
        "Account_Code",
        "PaymentID",
        "Reference",
        "Status",
        "CurrencyRate",
        "IsReconciled",
    ],
    "PurchaseOrders": [
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_Quantity",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
        "PurchaseOrderID",
        "PurchaseOrderNumber",
        "DateString",
        "DeliveryDateString",
        "Status",
        "CurrencyCode",
        "Reference",
        "LineItem_TaxType",
        "LineItem_ItemCode",
    ],
    "ManualJournals": [
        "Narration",
        "JournalLine_LineAmount",
        "JournalLine_AccountCode",
        "ManualJournalID",
        "DateString",
        "Status",
        "JournalLine_Description",
        "JournalLine_TaxType",
    ],
    "Items": [
        "Code",
        "Name",
        "Description",
        "IsSold",
        "IsPurchased",
        "SalesDetails_UnitPrice",
        "SalesDetails_AccountCode",
        "SalesDetails_TaxType",
        "PurchaseDetails_UnitPrice",
        "PurchaseDetails_AccountCode",
        "PurchaseDetails_TaxType",
        "ItemID",
        "PurchaseDescription",
    ],
    "CreditNotes": [
        "Type",
        "Status",
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_Quantity",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
        "CreditNoteID",
        "CreditNoteNumber",
        "Reference",
        "CurrencyCode",
        "DateString",
        "LineItem_TaxType",
        "LineItem_ItemCode",
    ],
    "Currencies": [
        "Code",
        "Description",
    ],
    "Employees": [
        "FirstName",
        "LastName",
        "EmployeeID",
        "Status",
    ],
    "Quotes": [
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_Quantity",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
        "QuoteID",
        "QuoteNumber",
        "Reference",
        "Status",
        "CurrencyCode",
        "DateString",
        "ExpiryDateString",
        "Title",
        "LineItem_TaxType",
        "LineItem_ItemCode",
    ],
    "TrackingCategories": [
        "Name",
        "TrackingCategoryID",
        "Status",
    ],
    "BankTransactions": [
        "Type",
        "BankAccount_Code",
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
        "BankTransactionID",
        "DateString",
        "Status",
        "Reference",
        "CurrencyCode",
        "LineItem_Quantity",
        "LineItem_TaxType",
        "LineItem_ItemCode",
        "IsReconciled",
    ],
}

# https://developer.xero.com/documentation/api/accounting/overview
# For either/or requirements (e.g. ContactID or Name), both are marked required.
ENTITY_FIELD_REQUIRED: dict[str, set[str]] = {
    "Contacts": {"Name"},
    "Invoices": {
        "Type",
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
        "DateString",
    },
    "Payments": {"Amount", "Date", "Invoice_InvoiceID", "Invoice_InvoiceNumber", "Account_Code"},
    "PurchaseOrders": {
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
    },
    "ManualJournals": {"Narration", "JournalLine_LineAmount", "JournalLine_AccountCode"},
    "Items": {"Code"},
    "CreditNotes": {
        "Type",
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
    },
    "Currencies": {"Code"},
    "Employees": {"FirstName", "LastName"},
    "Quotes": {
        "Contact_ContactID",
        "Contact_Name",
        "LineItem_Description",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
    },
    "TrackingCategories": {"Name"},
    "BankTransactions": {
        "Type",
        "BankAccount_Code",
        "LineItem_UnitAmount",
        "LineItem_AccountCode",
    },
}

# ------------------------------------------------------------------ #
# Entity configs + factory                                             #
# ------------------------------------------------------------------ #

ENTITY_CONFIGS: dict[EntityType, EntityConfig] = {
    EntityType.contacts: EntityConfig(
        entity_name="Contacts",
        row_to_model=_row_to_contact,
        collection_class=Contacts,
        collection_kwarg="contacts",
        result_attr="contacts",
        result_id_attr="name",
        create_method="create_contacts",
        upsert_method="update_or_create_contacts",
    ),
    EntityType.invoices: EntityConfig(
        entity_name="Invoices",
        row_to_model=_row_to_invoice,
        collection_class=Invoices,
        collection_kwarg="invoices",
        result_attr="invoices",
        result_id_attr="invoice_number",
        create_method="create_invoices",
        upsert_method="update_or_create_invoices",
    ),
    EntityType.payments: EntityConfig(
        entity_name="Payments",
        row_to_model=_row_to_payment,
        collection_class=Payments,
        collection_kwarg="payments",
        result_attr="payments",
        result_id_attr="payment_id",
        create_method="create_payments",
        # Xero API does not support updating payments — always create
    ),
    EntityType.purchase_orders: EntityConfig(
        entity_name="PurchaseOrders",
        row_to_model=_row_to_purchase_order,
        collection_class=PurchaseOrders,
        collection_kwarg="purchase_orders",
        result_attr="purchase_orders",
        result_id_attr="purchase_order_number",
        create_method="create_purchase_orders",
        upsert_method="update_or_create_purchase_orders",
    ),
    EntityType.manual_journals: EntityConfig(
        entity_name="ManualJournals",
        row_to_model=_row_to_manual_journal,
        collection_class=ManualJournals,
        collection_kwarg="manual_journals",
        result_attr="manual_journals",
        result_id_attr="narration",
        create_method="create_manual_journals",
        upsert_method="update_or_create_manual_journals",
    ),
    EntityType.items: EntityConfig(
        entity_name="Items",
        row_to_model=_row_to_item,
        collection_class=Items,
        collection_kwarg="items",
        result_attr="items",
        result_id_attr="code",
        create_method="create_items",
        upsert_method="update_or_create_items",
    ),
    EntityType.credit_notes: EntityConfig(
        entity_name="CreditNotes",
        row_to_model=_row_to_credit_note,
        collection_class=CreditNotes,
        collection_kwarg="credit_notes",
        result_attr="credit_notes",
        result_id_attr="credit_note_number",
        create_method="create_credit_notes",
        upsert_method="update_or_create_credit_notes",
    ),
    EntityType.employees: EntityConfig(
        entity_name="Employees",
        row_to_model=_row_to_employee,
        collection_class=Employees,
        collection_kwarg="employees",
        result_attr="employees",
        result_id_attr="employee_id",
        create_method="create_employees",
        upsert_method="update_or_create_employees",
        upsert_summarize=False,  # update_or_create_employees doesn't accept summarize_errors
        collect_errors=False,  # original EmployeesWriter did not collect validation errors
    ),
    EntityType.quotes: EntityConfig(
        entity_name="Quotes",
        row_to_model=_row_to_quote,
        collection_class=Quotes,
        collection_kwarg="quotes",
        result_attr="quotes",
        result_id_attr="quote_number",
        create_method="create_quotes",
        upsert_method="update_or_create_quotes",
    ),
    EntityType.bank_transactions: EntityConfig(
        entity_name="BankTransactions",
        row_to_model=_row_to_bank_transaction,
        collection_class=BankTransactions,
        collection_kwarg="bank_transactions",
        result_attr="bank_transactions",
        result_id_attr="bank_transaction_id",
        create_method="create_bank_transactions",
        upsert_method="update_or_create_bank_transactions",
    ),
}


def build_writer(entity_type: EntityType, api_client: ApiClient, tenant_id: str, write_mode: str) -> BaseWriter:
    """Factory: return the appropriate writer for the given entity type."""
    if entity_type == EntityType.currencies:
        return CurrenciesWriter(api_client, tenant_id, write_mode)
    if entity_type == EntityType.tracking_categories:
        return TrackingCategoriesWriter(api_client, tenant_id, write_mode)
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        raise UserException(f"Unsupported entity type: '{entity_type.value}'")
    return GenericWriter(config, api_client, tenant_id, write_mode)
