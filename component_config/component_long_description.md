# Xero Accounting Writer

Write data from Keboola Connection Storage back to [Xero Accounting](https://www.xero.com/) via the Xero API.

## Supported entities

| Entity | Create | Upsert |
|--------|--------|--------|
| Contacts | ✓ | ✓ |
| Invoices | ✓ | ✓ |
| Payments | ✓ | ✓ |
| Purchase Orders | ✓ | ✓ |
| Manual Journals | ✓ | ✓ |
| Items | ✓ | ✓ |
| Credit Notes | ✓ | ✓ |
| Currencies | ✓ | — |
| Employees | ✓ | ✓ |
| Quotes | ✓ | ✓ |
| Tracking Categories | ✓ | ✓ |
| Bank Transactions | ✓ | ✓ |

## Write modes

- **Create** — POST new records; fails if the record already exists.
- **Upsert** — POST or PUT; creates new records or updates existing ones using Xero's native ID or reference number (e.g. `ContactNumber`, `InvoiceNumber`).

## Authentication

Uses Xero OAuth 2.0. Authorize once via the Keboola OAuth proxy; tokens are automatically refreshed.

## Notes

- Budget writes are **not supported** by the Xero API (`/Budgets` is read-only).
- Rate limit: 50 requests per 60 seconds (handled automatically).
- Records are sent in batches of up to 100 per API call.
