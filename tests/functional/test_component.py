"""
Functional tests for the Xero Accounting Writer component.

These tests validate the component's configuration parsing, writer routing,
and CSV-to-model mapping logic WITHOUT making real Xero API calls.
"""
import os
import sys
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

# Ensure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from configuration import EntityType, RootConfiguration, RowConfiguration, WriteMode
from writers.base_writer import _is_empty, _to_bool, _to_float, _to_int


class TestBaseWriterHelpers(unittest.TestCase):
    """Unit tests for shared CSV conversion helpers."""

    def test_is_empty_none(self):
        self.assertTrue(_is_empty(None))

    def test_is_empty_blank_string(self):
        self.assertTrue(_is_empty(""))
        self.assertTrue(_is_empty("   "))

    def test_is_empty_valid_value(self):
        self.assertFalse(_is_empty("hello"))
        self.assertFalse(_is_empty("0"))
        self.assertFalse(_is_empty(0))

    def test_to_bool_true_variants(self):
        for v in ("true", "True", "TRUE", "1", "yes", "YES"):
            self.assertTrue(_to_bool(v), f"Expected True for '{v}'")

    def test_to_bool_false_variants(self):
        for v in ("false", "False", "FALSE", "0", "no", "NO"):
            self.assertFalse(_to_bool(v), f"Expected False for '{v}'")

    def test_to_bool_empty(self):
        self.assertIsNone(_to_bool(""))
        self.assertIsNone(_to_bool(None))

    def test_to_float_valid(self):
        self.assertEqual(_to_float("3.14"), 3.14)
        self.assertEqual(_to_float("100"), 100.0)

    def test_to_float_empty(self):
        self.assertIsNone(_to_float(""))
        self.assertIsNone(_to_float(None))

    def test_to_float_invalid(self):
        self.assertIsNone(_to_float("not_a_number"))

    def test_to_int_valid(self):
        self.assertEqual(_to_int("42"), 42)
        self.assertEqual(_to_int("3.9"), 3)

    def test_to_int_empty(self):
        self.assertIsNone(_to_int(""))
        self.assertIsNone(_to_int(None))


class TestConfiguration(unittest.TestCase):
    """Unit tests for configuration models."""

    def test_row_config_defaults(self):
        config = RowConfiguration(entity_type="Contacts")
        self.assertEqual(config.entity_type, EntityType.contacts)
        self.assertEqual(config.write_mode, WriteMode.upsert)

    def test_row_config_create_mode(self):
        config = RowConfiguration(entity_type="Invoices", write_mode="create")
        self.assertEqual(config.entity_type, EntityType.invoices)
        self.assertEqual(config.write_mode, WriteMode.create)

    def test_row_config_all_entity_types(self):
        entity_types = [
            "Contacts", "Invoices", "Payments", "PurchaseOrders",
            "ManualJournals", "Items", "CreditNotes", "Currencies",
            "Employees", "Quotes", "TrackingCategories", "BankTransactions",
        ]
        for et in entity_types:
            config = RowConfiguration(entity_type=et)
            self.assertIsNotNone(config.entity_type, f"Failed for entity_type={et}")

    def test_root_config_optional_tenant(self):
        config = RootConfiguration()
        self.assertIsNone(config.tenant_id)

    def test_root_config_with_tenant(self):
        config = RootConfiguration(tenant_id="abc-123")
        self.assertEqual(config.tenant_id, "abc-123")


class TestContactsWriter(unittest.TestCase):
    """Unit tests for ContactsWriter model mapping."""

    def setUp(self):
        from writers.contacts import ContactsWriter
        mock_api_client = MagicMock()
        with patch("writers.base_writer.AccountingApi"):
            self.writer = ContactsWriter(mock_api_client, "tenant-123", "upsert")

    def test_row_to_contact_basic(self):
        row: Dict[str, Any] = {
            "Name": "Acme Corp",
            "EmailAddress": "acme@example.com",
            "ContactNumber": "C001",
            "IsCustomer": "true",
            "IsSupplier": "false",
        }
        contact = self.writer._row_to_contact(row)
        self.assertEqual(contact.name, "Acme Corp")
        self.assertEqual(contact.email_address, "acme@example.com")
        self.assertEqual(contact.contact_number, "C001")
        self.assertTrue(contact.is_customer)
        self.assertFalse(contact.is_supplier)

    def test_row_to_contact_skips_empty(self):
        row: Dict[str, Any] = {"Name": "Test", "EmailAddress": ""}
        contact = self.writer._row_to_contact(row)
        self.assertEqual(contact.name, "Test")
        self.assertIsNone(contact.email_address)

    def test_row_to_contact_with_phone(self):
        row: Dict[str, Any] = {
            "Name": "Phone Corp",
            "Phone_PhoneNumber": "555-1234",
            "Phone_PhoneType": "DEFAULT",
        }
        contact = self.writer._row_to_contact(row)
        self.assertIsNotNone(contact.phones)
        self.assertEqual(len(contact.phones), 1)
        self.assertEqual(contact.phones[0].phone_number, "555-1234")

    def test_row_to_contact_no_phone_when_empty(self):
        row: Dict[str, Any] = {"Name": "No Phone Corp", "Phone_PhoneNumber": ""}
        contact = self.writer._row_to_contact(row)
        self.assertIsNone(contact.phones)


class TestInvoicesWriter(unittest.TestCase):
    """Unit tests for InvoicesWriter model mapping."""

    def setUp(self):
        from writers.invoices import InvoicesWriter
        mock_api_client = MagicMock()
        with patch("writers.base_writer.AccountingApi"):
            self.writer = InvoicesWriter(mock_api_client, "tenant-123", "upsert")

    def test_row_to_invoice_basic(self):
        row: Dict[str, Any] = {
            "InvoiceNumber": "INV-001",
            "Type": "ACCREC",
            "Status": "DRAFT",
            "Contact_Name": "Customer A",
            "LineItem_Description": "Consulting services",
            "LineItem_UnitAmount": "100.00",
            "LineItem_Quantity": "5",
            "LineItem_AccountCode": "200",
        }
        invoice = self.writer._row_to_invoice(row)
        self.assertEqual(invoice.invoice_number, "INV-001")
        self.assertEqual(invoice.type, "ACCREC")
        self.assertIsNotNone(invoice.contact)
        self.assertEqual(invoice.contact.name, "Customer A")
        self.assertIsNotNone(invoice.line_items)
        self.assertEqual(invoice.line_items[0].unit_amount, 100.0)
        self.assertEqual(invoice.line_items[0].quantity, 5.0)


class TestWriterRouting(unittest.TestCase):
    """Test that component correctly routes to the right writer."""

    def test_writer_map_completeness(self):
        from component import WRITER_MAP
        for entity in EntityType:
            self.assertIn(entity, WRITER_MAP, f"Missing writer for {entity}")


if __name__ == "__main__":
    unittest.main()
