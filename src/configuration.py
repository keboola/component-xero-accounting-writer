from enum import Enum
from typing import Optional

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class WriteMode(str, Enum):
    create = "create"
    upsert = "upsert"


class EntityType(str, Enum):
    contacts = "Contacts"
    invoices = "Invoices"
    payments = "Payments"
    purchase_orders = "PurchaseOrders"
    manual_journals = "ManualJournals"
    items = "Items"
    credit_notes = "CreditNotes"
    currencies = "Currencies"
    employees = "Employees"
    quotes = "Quotes"
    tracking_categories = "TrackingCategories"
    bank_transactions = "BankTransactions"


class RootConfiguration(BaseModel):
    """Root-level configuration (shared across all rows)."""

    tenant_id: Optional[str] = Field(default=None)

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Configuration validation error: {', '.join(error_messages)}") from e


class RowConfiguration(BaseModel):
    """Per-row configuration (one entity type to write)."""

    entity_type: EntityType
    write_mode: WriteMode = WriteMode.upsert

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Row configuration validation error: {', '.join(error_messages)}") from e
