Xero Accounting Writer
======================

Writes accounting data to [Xero](https://www.xero.com/) via the Xero Accounting API.
Supports 12 entity types, each mapped from a flat CSV input table.

**Table of Contents:**

- [Supported Entities](#supported-entities)
- [Configuration](#configuration)
  - [Root Configuration](#root-configuration)
  - [Entities Array](#entities-array)
  - [Example](#example)
- [Input Tables](#input-tables)
  - [Contacts](#contacts)
  - [Invoices](#invoices)
  - [Payments](#payments)
  - [Purchase Orders](#purchase-orders)
  - [Manual Journals](#manual-journals)
  - [Items](#items)
  - [Credit Notes](#credit-notes)
  - [Currencies](#currencies)
  - [Employees](#employees)
  - [Quotes](#quotes)
  - [Tracking Categories](#tracking-categories)
  - [Bank Transactions](#bank-transactions)
- [Write Modes](#write-modes)
- [Authentication](#authentication)
- [Development](#development)

---

Supported Entities
==================

| Entity Type | Xero Object |
|---|---|
| `Contacts` | Suppliers and customers |
| `Invoices` | Accounts receivable / payable invoices |
| `Payments` | Invoice payments |
| `PurchaseOrders` | Purchase orders |
| `ManualJournals` | Manual journal entries |
| `Items` | Product / service catalogue |
| `CreditNotes` | Credit notes |
| `Currencies` | Organisation currencies |
| `Employees` | Basic employee records |
| `Quotes` | Sales quotes |
| `TrackingCategories` | Tracking categories |
| `BankTransactions` | Spend / receive money transactions |

---

Configuration
=============

Root Configuration
------------------

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tenant_id` | string | No | Xero organisation (tenant) ID. If omitted, the first available tenant is used. |
| `entities` | array | Yes | List of entities to write (see below). |

Entities Array
--------------

Each item in the `entities` array configures one entity to write:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entity_type` | string | Yes | One of the 12 supported entity types (e.g. `Contacts`). |
| `write_mode` | string | Yes | `upsert` (default) or `create`. |
| `source_table` | string | Yes | Destination name of the input table as set in the storage mapping. |

Example
-------

```json
{
  "parameters": {
    "tenant_id": "your-xero-tenant-id",
    "entities": [
      {
        "entity_type": "Contacts",
        "write_mode": "upsert",
        "source_table": "contacts"
      },
      {
        "entity_type": "Invoices",
        "write_mode": "create",
        "source_table": "invoices"
      }
    ]
  }
}
```

All entities are processed in a single run using one OAuth session. The input table name in `source_table` must exactly match the destination name configured in the **Input Mapping** of the component.

---

Input Tables
============

Each entity type expects a flat CSV table. Empty cells are ignored — only non-empty values are sent to the API. The `*ID` columns are used for matching during upsert.

Contacts
--------

| Column | Type | Notes |
|---|---|---|
| `ContactID` | string | Xero GUID — used for upsert matching |
| `ContactNumber` | string | Your internal reference |
| `AccountNumber` | string | |
| `ContactStatus` | string | `ACTIVE` or `ARCHIVED` |
| `Name` | string | **Required** |
| `FirstName` | string | |
| `LastName` | string | |
| `EmailAddress` | string | |
| `BankAccountDetails` | string | |
| `TaxNumber` | string | |
| `AccountsReceivableTaxType` | string | |
| `AccountsPayableTaxType` | string | |
| `IsSupplier` | boolean | `true`/`false` |
| `IsCustomer` | boolean | `true`/`false` |
| `DefaultCurrency` | string | ISO 4217 code |
| `Website` | string | |
| `Phone_PhoneNumber` | string | |
| `Phone_PhoneType` | string | `DEFAULT`, `DDI`, `FAX`, `MOBILE`, `OFFICE` |
| `Phone_PhoneAreaCode` | string | |
| `Phone_PhoneCountryCode` | string | |
| `Address_AddressType` | string | `STREET` or `POBOX` |
| `Address_AddressLine1` | string | |
| `Address_AddressLine2` | string | |
| `Address_AddressLine3` | string | |
| `Address_AddressLine4` | string | |
| `Address_City` | string | |
| `Address_Region` | string | |
| `Address_PostalCode` | string | |
| `Address_Country` | string | |
| `Address_AttentionTo` | string | |

Invoices
--------

| Column | Type | Notes |
|---|---|---|
| `InvoiceID` | string | Xero GUID — used for upsert matching |
| `InvoiceNumber` | string | Your reference — used for upsert matching |
| `Type` | string | `ACCREC` (receivable) or `ACCPAY` (payable) |
| `Status` | string | `DRAFT`, `SUBMITTED`, `AUTHORISED`, `PAID`, `VOIDED` |
| `Reference` | string | |
| `CurrencyCode` | string | ISO 4217 |
| `CurrencyRate` | number | |
| `Url` | string | |
| `DateString` | string | `YYYY-MM-DD` |
| `DueDateString` | string | `YYYY-MM-DD` |
| `BrandingThemeID` | string | |
| `Contact_ContactID` | string | Xero contact GUID |
| `Contact_Name` | string | Contact name (used if no ContactID) |
| `LineItem_Description` | string | **Required for line item** |
| `LineItem_Quantity` | number | |
| `LineItem_UnitAmount` | number | |
| `LineItem_AccountCode` | string | |
| `LineItem_TaxType` | string | |
| `LineItem_ItemCode` | string | |
| `LineItem_DiscountRate` | number | |
| `LineItem_LineItemID` | string | |

Payments
--------

| Column | Type | Notes |
|---|---|---|
| `PaymentID` | string | Xero GUID — used for upsert matching |
| `Date` | string | `YYYY-MM-DD` |
| `Amount` | number | |
| `CurrencyRate` | number | |
| `Reference` | string | |
| `IsReconciled` | boolean | |
| `Status` | string | `AUTHORISED`, `DELETED` |
| `PaymentType` | string | |
| `Invoice_InvoiceID` | string | Xero GUID of the invoice |
| `Invoice_InvoiceNumber` | string | Invoice number (used if no InvoiceID) |
| `Account_AccountID` | string | Xero GUID of bank account |
| `Account_Code` | string | Account code (used if no AccountID) |

Purchase Orders
---------------

| Column | Type | Notes |
|---|---|---|
| `PurchaseOrderID` | string | Xero GUID — used for upsert matching |
| `PurchaseOrderNumber` | string | |
| `Status` | string | `DRAFT`, `SUBMITTED`, `AUTHORISED`, `BILLED`, `DELETED` |
| `DateString` | string | `YYYY-MM-DD` |
| `DeliveryDateString` | string | `YYYY-MM-DD` |
| `Reference` | string | |
| `CurrencyCode` | string | |
| `CurrencyRate` | number | |
| `AttentionTo` | string | |
| `Telephone` | string | |
| `DeliveryAddress` | string | |
| `DeliveryInstructions` | string | |
| `Contact_ContactID` | string | |
| `Contact_Name` | string | |
| `LineItem_Description` | string | **Required for line item** |
| `LineItem_Quantity` | number | |
| `LineItem_UnitAmount` | number | |
| `LineItem_AccountCode` | string | |
| `LineItem_TaxType` | string | |
| `LineItem_ItemCode` | string | |

Manual Journals
---------------

| Column | Type | Notes |
|---|---|---|
| `ManualJournalID` | string | Xero GUID — used for upsert matching |
| `Narration` | string | **Required** |
| `DateString` | string | `YYYY-MM-DD` |
| `Status` | string | `DRAFT`, `POSTED`, `VOIDED` |
| `Url` | string | |
| `ShowOnCashBasisReports` | boolean | |
| `JournalLine_AccountCode` | string | **Required for journal line** |
| `JournalLine_LineAmount` | number | Positive = debit, negative = credit |
| `JournalLine_Description` | string | |
| `JournalLine_TaxType` | string | |

Items
-----

| Column | Type | Notes |
|---|---|---|
| `ItemID` | string | Xero GUID — used for upsert matching |
| `Code` | string | **Required** — your item code |
| `Name` | string | |
| `Description` | string | Sales description |
| `PurchaseDescription` | string | |
| `IsSold` | boolean | |
| `IsPurchased` | boolean | |
| `SalesDetails_UnitPrice` | number | |
| `SalesDetails_AccountCode` | string | |
| `SalesDetails_TaxType` | string | |
| `PurchaseDetails_UnitPrice` | number | |
| `PurchaseDetails_AccountCode` | string | |
| `PurchaseDetails_TaxType` | string | |

Credit Notes
------------

| Column | Type | Notes |
|---|---|---|
| `CreditNoteID` | string | Xero GUID — used for upsert matching |
| `CreditNoteNumber` | string | |
| `Type` | string | `ACCRECCREDIT` or `ACCPAYCREDIT` |
| `Status` | string | `DRAFT`, `SUBMITTED`, `AUTHORISED`, `PAID`, `VOIDED` |
| `Reference` | string | |
| `DateString` | string | `YYYY-MM-DD` |
| `CurrencyCode` | string | |
| `CurrencyRate` | number | |
| `BrandingThemeID` | string | |
| `Contact_ContactID` | string | |
| `Contact_Name` | string | |
| `LineItem_Description` | string | **Required for line item** |
| `LineItem_Quantity` | number | |
| `LineItem_UnitAmount` | number | |
| `LineItem_AccountCode` | string | |
| `LineItem_TaxType` | string | |
| `LineItem_ItemCode` | string | |

Currencies
----------

| Column | Type | Notes |
|---|---|---|
| `Code` | string | **Required** — ISO 4217 currency code |
| `Description` | string | |

Employees
---------

| Column | Type | Notes |
|---|---|---|
| `EmployeeID` | string | Xero GUID — used for upsert matching |
| `FirstName` | string | **Required** |
| `LastName` | string | **Required** |
| `Status` | string | `ACTIVE` or `TERMINATED` |

Quotes
------

| Column | Type | Notes |
|---|---|---|
| `QuoteID` | string | Xero GUID — used for upsert matching |
| `QuoteNumber` | string | |
| `Status` | string | `DRAFT`, `SENT`, `DECLINED`, `ACCEPTED`, `INVOICED`, `DELETED` |
| `Title` | string | |
| `Summary` | string | |
| `Terms` | string | |
| `Reference` | string | |
| `DateString` | string | `YYYY-MM-DD` |
| `ExpiryDateString` | string | `YYYY-MM-DD` |
| `CurrencyCode` | string | |
| `CurrencyRate` | number | |
| `Contact_ContactID` | string | |
| `Contact_Name` | string | |
| `LineItem_Description` | string | **Required for line item** |
| `LineItem_Quantity` | number | |
| `LineItem_UnitAmount` | number | |
| `LineItem_AccountCode` | string | |
| `LineItem_TaxType` | string | |
| `LineItem_ItemCode` | string | |

Tracking Categories
-------------------

| Column | Type | Notes |
|---|---|---|
| `TrackingCategoryID` | string | Xero GUID — used for upsert matching |
| `Name` | string | **Required** |
| `Status` | string | `ACTIVE` or `ARCHIVED` |

Bank Transactions
-----------------

| Column | Type | Notes |
|---|---|---|
| `BankTransactionID` | string | Xero GUID — used for upsert matching |
| `Type` | string | `SPEND` or `RECEIVE` |
| `Status` | string | `AUTHORISED`, `DELETED` |
| `Reference` | string | |
| `DateString` | string | `YYYY-MM-DD` |
| `Url` | string | |
| `IsReconciled` | boolean | |
| `CurrencyCode` | string | |
| `CurrencyRate` | number | |
| `Contact_ContactID` | string | |
| `Contact_Name` | string | |
| `BankAccount_AccountID` | string | Xero GUID of bank account |
| `BankAccount_Code` | string | Account code (used if no AccountID) |
| `LineItem_Description` | string | **Required for line item** |
| `LineItem_Quantity` | number | |
| `LineItem_UnitAmount` | number | |
| `LineItem_AccountCode` | string | |
| `LineItem_TaxType` | string | |
| `LineItem_ItemCode` | string | |

---

Write Modes
===========

| Mode | Behaviour |
|---|---|
| `upsert` | Creates new records or updates existing ones. Matching is done by Xero ID (e.g. `ContactID`) or by a natural key (e.g. `ContactNumber`, `InvoiceNumber`). |
| `create` | Only creates new records. Fails if a duplicate already exists in Xero. |

---

Authentication
==============

The component uses **OAuth 2.0** via Keboola's built-in OAuth broker. Authorize the component in the Keboola UI before running it. The access token is automatically refreshed and stored in component state between runs.

If a run fails with an authorization error, reauthorize the component in the UI before retrying — the token may have been invalidated.

---

Development
===========

**Prerequisites:** [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

**Project structure:**

```
src/
  component.py        # Entry point, entity iteration loop
  configuration.py    # Pydantic config models
  client/             # Xero OAuth2 client wrapper
  writers/
    base_writer.py    # Shared batch logic and CSV helpers
    contacts.py
    invoices.py
    payments.py
    purchase_orders.py
    manual_journals.py
    items.py
    credit_notes.py
    currencies.py
    employees.py
    quotes.py
    tracking_categories.py
    bank_transactions.py
```

For deployment details see the [Keboola developer documentation](https://developers.keboola.com/extend/component/deployment/).
