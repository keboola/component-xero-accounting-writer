import logging
from typing import Any

from keboola.component.exceptions import UserException
from xero_python.accounting.models import Address, Contact, Contacts, CurrencyCode, Phone
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty, _to_bool


class ContactsWriter(BaseWriter):
    """Writes Contact records to Xero.

    Supported CSV columns (maps directly to Xero Contact fields):
      ContactID, ContactNumber, AccountNumber, ContactStatus, Name, FirstName, LastName,
      EmailAddress, BankAccountDetails, TaxNumber, AccountsReceivableTaxType,
      AccountsPayableTaxType, IsSupplier, IsCustomer, DefaultCurrency,
      Website, BatchPayments, Discount, HasAttachments, HasValidationErrors,
      Phone_PhoneType, Phone_PhoneNumber, Phone_PhoneAreaCode, Phone_PhoneCountryCode,
      Address_AddressType, Address_AddressLine1, Address_AddressLine2, Address_AddressLine3,
      Address_AddressLine4, Address_City, Address_Region, Address_PostalCode, Address_Country,
      Address_AttentionTo
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: list[dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} contact(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        contacts = [self._row_to_contact(row) for row in batch]
        contacts_obj = Contacts(contacts=contacts)
        try:
            if self.write_mode == "upsert":
                result = self.accounting_api.update_or_create_contacts(
                    self.tenant_id,
                    contacts_obj,
                    summarize_errors=False,
                )
            else:
                result = self.accounting_api.create_contacts(
                    self.tenant_id,
                    contacts_obj,
                    summarize_errors=False,
                )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write contacts batch: {exc}")
            raise UserException(f"Failed to write contacts batch: {exc}") from exc

    def _row_to_contact(self, row: dict[str, Any]) -> Contact:
        contact = Contact()

        if v := self._get(row, "ContactID"):
            contact.contact_id = v
        if v := self._get(row, "ContactNumber"):
            contact.contact_number = v
        if v := self._get(row, "AccountNumber"):
            contact.account_number = v
        if v := self._get(row, "ContactStatus"):
            contact.contact_status = v
        if v := self._get(row, "Name"):
            contact.name = v
        if v := self._get(row, "FirstName"):
            contact.first_name = v
        if v := self._get(row, "LastName"):
            contact.last_name = v
        if v := self._get(row, "EmailAddress"):
            contact.email_address = v
        if v := self._get(row, "BankAccountDetails"):
            contact.bank_account_details = v
        if v := self._get(row, "TaxNumber"):
            contact.tax_number = v
        if v := self._get(row, "AccountsReceivableTaxType"):
            contact.accounts_receivable_tax_type = v
        if v := self._get(row, "AccountsPayableTaxType"):
            contact.accounts_payable_tax_type = v
        if v := self._get(row, "DefaultCurrency"):
            contact.default_currency = CurrencyCode(v)
        if v := self._get(row, "Website"):
            contact.website = v

        is_supplier = _to_bool(row.get("IsSupplier"))
        if is_supplier is not None:
            contact.is_supplier = is_supplier

        is_customer = _to_bool(row.get("IsCustomer"))
        if is_customer is not None:
            contact.is_customer = is_customer

        phone = self._build_phone(row)
        if phone:
            contact.phones = [phone]

        address = self._build_address(row)
        if address:
            contact.addresses = [address]

        return contact

    @staticmethod
    def _build_phone(row: dict[str, Any]) -> Phone | None:
        phone_number = row.get("Phone_PhoneNumber")
        if _is_empty(phone_number):
            return None
        phone = Phone(phone_number=str(phone_number).strip())
        if v := row.get("Phone_PhoneType"):
            if not _is_empty(v):
                phone.phone_type = str(v).strip()
        if v := row.get("Phone_PhoneAreaCode"):
            if not _is_empty(v):
                phone.phone_area_code = str(v).strip()
        if v := row.get("Phone_PhoneCountryCode"):
            if not _is_empty(v):
                phone.phone_country_code = str(v).strip()
        return phone

    @staticmethod
    def _build_address(row: dict[str, Any]) -> Address | None:
        has_address = any(
            not _is_empty(row.get(k))
            for k in (
                "Address_AddressLine1",
                "Address_City",
                "Address_PostalCode",
                "Address_Country",
            )
        )
        if not has_address:
            return None
        address = Address()
        if v := row.get("Address_AddressType"):
            if not _is_empty(v):
                address.address_type = str(v).strip()
        for field, attr in [
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
            v = row.get(field)
            if not _is_empty(v):
                setattr(address, attr, str(v).strip())
        return address

    @staticmethod
    def _log_result(result) -> None:
        if hasattr(result, "contacts") and result.contacts:
            ok = sum(1 for c in result.contacts if not c.validation_errors)
            errors = [c for c in result.contacts if c.validation_errors]
            logging.info(f"Contacts batch: {ok} ok, {len(errors)} with validation errors")
            for c in errors:
                logging.warning(f"  Contact '{c.name}' validation errors: {c.validation_errors}")
