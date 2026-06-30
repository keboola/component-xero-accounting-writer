from enum import StrEnum

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class WriteMode(StrEnum):
    create = "create"
    upsert = "upsert"


class EntityType(StrEnum):
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


class ColumnMapping(BaseModel):
    """Maps a single source column to a Xero field name."""

    source: str
    destination: str
    required: bool | None = Field(default=None)


class EntityConfiguration(BaseModel):
    """Configuration for a single entity to write."""

    entity_type: EntityType
    write_mode: WriteMode = WriteMode.upsert
    source_table: str
    column_mapping: list[ColumnMapping] = Field(default_factory=list)

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Entity configuration validation error: {', '.join(error_messages)}") from e


class RootConfiguration(BaseModel):
    """Root-level configuration."""

    tenant_id: str | None = Field(default=None)
    skip_validation_errors: bool = Field(default=False)
    create_errors_table: bool = Field(default=False)
    entities: list[EntityConfiguration] = Field(default_factory=list)

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Configuration validation error: {', '.join(error_messages)}") from e
