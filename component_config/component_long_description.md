The Xero Accounting Writer enables seamless synchronisation of data from Keboola Storage into [Xero](https://www.xero.com/), a cloud-based accounting platform trusted by millions of businesses worldwide. Whether you are automating the creation of invoices, syncing supplier contacts from a CRM, importing payroll employees, or pushing journal entries from an external system, this component provides a unified, configuration-driven way to write accounting data to Xero without custom code.

All entity types are processed in a single component run using one OAuth session, eliminating token conflicts when writing multiple tables. Each entity is configured with its own source table and write mode, giving you precise control over which data flows to Xero and how.

**Supported entity types:**

- **Contacts** — Suppliers and customers with addresses and phone numbers
- **Invoices** — Accounts receivable and payable invoices with line items
- **Payments** — Invoice payment records linked to bank accounts
- **Purchase Orders** — Supplier purchase orders with line items and delivery details
- **Manual Journals** — Custom journal entries for bookkeeping adjustments
- **Items** — Product and service catalogue with sales and purchase pricing
- **Credit Notes** — Credit notes for receivable and payable accounts
- **Currencies** — Organisation currency configuration
- **Employees** — Basic employee records for payroll integration
- **Quotes** — Sales quotes with expiry dates and line items
- **Tracking Categories** — Custom tracking dimensions for reporting
- **Bank Transactions** — Spend and receive money transactions

**Key features:**

- **Upsert and create modes** — Upsert creates new records or updates existing ones by Xero ID or natural key; create mode adds new records only
- **Single OAuth session** — All entities are written in one execution, avoiding multiple token refresh cycles
- **Multi-tenant support** — Specify a Tenant ID explicitly or let the component auto-select the first available Xero organisation
- **Flat CSV input** — Each entity maps from a flat CSV table using named columns; empty cells are safely ignored
- **Batch processing** — Records are submitted in batches with per-record validation error reporting
- **Automatic token refresh** — The OAuth token is refreshed at startup and the new token is persisted to component state for subsequent runs
