import csv
import json
import logging

import requests
from keboola.component.base import ComponentBase, sync_action
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement

from client import XeroClient, XeroException
from configuration import ColumnMapping, EntityType, RootConfiguration
from writers import (
    BankTransactionsWriter,
    BaseWriter,
    ContactsWriter,
    CreditNotesWriter,
    CurrenciesWriter,
    EmployeesWriter,
    InvoicesWriter,
    ItemsWriter,
    ManualJournalsWriter,
    PaymentsWriter,
    PurchaseOrdersWriter,
    QuotesWriter,
    TrackingCategoriesWriter,
)

KEY_STATE_OAUTH_TOKEN_DICT = "#oauth_token_dict"

# Required and commonly-used fields for each Xero entity type.
# Used by the loadFieldSuggestions sync action to pre-fill column_mapping.
# Fields are ordered: required first, then recommended optional ones.
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

# Required fields per entity type, based on Xero API documentation.
# https://developer.xero.com/documentation/api/accounting/overview
# For either/or requirements (e.g. ContactID or Name), both are marked required
# so the user knows at least one must be provided.
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

WRITER_MAP: dict[EntityType, type] = {
    EntityType.contacts: ContactsWriter,
    EntityType.invoices: InvoicesWriter,
    EntityType.payments: PaymentsWriter,
    EntityType.purchase_orders: PurchaseOrdersWriter,
    EntityType.manual_journals: ManualJournalsWriter,
    EntityType.items: ItemsWriter,
    EntityType.credit_notes: CreditNotesWriter,
    EntityType.currencies: CurrenciesWriter,
    EntityType.employees: EmployeesWriter,
    EntityType.quotes: QuotesWriter,
    EntityType.tracking_categories: TrackingCategoriesWriter,
    EntityType.bank_transactions: BankTransactionsWriter,
}


class Component(ComponentBase):
    def __init__(self, data_path_override: str = None) -> None:
        self.client: XeroClient = None  # type: ignore[assignment]
        super().__init__(data_path_override=data_path_override)

    def run(self) -> None:
        self._init_client()

        root_config = RootConfiguration(**self.configuration.parameters)
        tenant_id = self._resolve_tenant_id(root_config.tenant_id)

        if not root_config.entities:
            raise UserException("No entities configured. Add at least one entity in the 'Entities to Write' list.")

        input_tables = {t.name.removesuffix(".csv"): t for t in self.get_input_tables_definitions()}

        all_validation_errors: list[dict] = []

        for entity_cfg in root_config.entities:
            source_key = entity_cfg.source_table.removesuffix(".csv")
            table_def = input_tables.get(source_key)
            if table_def is None:
                raise UserException(
                    f"Input table '{entity_cfg.source_table}' not found for entity "
                    f"'{entity_cfg.entity_type.value}'. Check storage mapping."
                )
            rows = self._read_csv(table_def.full_path)
            logging.info(f"[{entity_cfg.entity_type.value}] Loaded {len(rows)} row(s) from '{entity_cfg.source_table}'")
            if entity_cfg.column_mapping:
                rows = self._apply_column_mapping(rows, entity_cfg.column_mapping)
                logging.info(
                    f"[{entity_cfg.entity_type.value}] Applied column mapping: {len(entity_cfg.column_mapping)} column(s)"
                )

            writer = self._build_writer(entity_cfg.entity_type, entity_cfg.write_mode.value, tenant_id)
            writer.write(rows)

            if writer.collected_errors:
                all_validation_errors.extend(writer.collected_errors)
                if not root_config.skip_validation_errors:
                    if root_config.create_errors_table:
                        self._write_validation_errors_table(all_validation_errors)
                    raise UserException(
                        f"Validation errors occurred in {len(writer.collected_errors)} record(s) "
                        f"for entity '{entity_cfg.entity_type.value}'. "
                        "Check the job logs for details or enable 'Create Errors Table' to export them."
                    )

        if all_validation_errors and root_config.create_errors_table:
            self._write_validation_errors_table(all_validation_errors)

        self._refresh_token_and_save_state()

    # ------------------------------------------------------------------ #
    # Auth helpers                                                          #
    # ------------------------------------------------------------------ #

    def _init_client(self) -> None:
        logging.info("Initializing Xero client")
        state = self.get_state_file()
        state_token = state.get(KEY_STATE_OAUTH_TOKEN_DICT)

        if self._state_has_valid_token(state_token):
            logging.info("Restoring client from saved state token")
            self._init_client_from_state(state_token)
        else:
            logging.info("Initializing client from OAuth credentials")
            self._init_client_from_config()

    def _init_client_from_state(self, state_token: str | dict) -> None:
        oauth_credentials = self.configuration.oauth_credentials
        if oauth_credentials is None:
            logging.warning("No OAuth credentials in config, cannot restore from state — falling back")
            self._init_client_from_config()
            return
        oauth_credentials.data = self._parse_state_token(state_token)
        self.client = XeroClient(oauth_credentials)
        try:
            self._refresh_token_and_save_state()
            self.client.get_available_tenant_ids()
        except (UserException, XeroException):
            logging.warning("State token init failed, falling back to OAuth credentials")
            self._init_client_from_config()

    def _init_client_from_config(self) -> None:
        oauth_credentials = self.configuration.oauth_credentials
        if oauth_credentials is None:
            raise UserException("No OAuth credentials found. Please authorize the component before running.")
        if isinstance(oauth_credentials.data.get("scope"), str):
            oauth_credentials.data["scope"] = oauth_credentials.data["scope"].split(" ")
        self.client = XeroClient(oauth_credentials)
        try:
            self._refresh_token_and_save_state()
            self.client.get_available_tenant_ids()
        except (UserException, XeroException) as exc:
            raise UserException(
                "Failed to authorize the component. Please reauthorize."
                "\nNote: if a Xero component fails, you must reauthorize before retrying."
            ) from exc

    def _refresh_token_and_save_state(self) -> None:
        try:
            self.client.force_refresh_token()
        except XeroException as exc:
            raise UserException("Failed to refresh the Xero token. Please reauthorize the component.") from exc
        new_state = self.get_state_file()
        new_state[KEY_STATE_OAUTH_TOKEN_DICT] = json.dumps(self.client.get_xero_oauth2_token_dict())
        self.write_state_file(new_state)

    def _save_config_state_via_api(self) -> None:
        """Persist current state to Keboola Storage API.

        Sync actions do not persist local state files automatically.
        This call ensures the refreshed OAuth token survives across runs.
        """
        storage_url = self.environment_variables.url
        token = self.environment_variables.token
        component_id = self.environment_variables.component_id
        config_id = self.environment_variables.config_id

        if not all([storage_url, token, component_id, config_id]):
            logging.debug("Missing KBC environment variables — skipping Storage API state persist")
            return

        state = self.get_state_file()
        url = f"{storage_url}/v2/storage/branch/default/components/{component_id}/configs/{config_id}/state"
        headers = {"X-StorageApi-Token": token, "Content-Type": "application/json"}
        payload = {"state": {"component": state}}

        try:
            response = requests.put(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            logging.info("Configuration state persisted to Storage API")
        except Exception as exc:
            logging.error(f"Failed to save configuration state to Storage API: {exc}")

    @staticmethod
    def _state_has_valid_token(state_token) -> bool:
        if not state_token:
            return False
        if isinstance(state_token, str):
            try:
                token = json.loads(state_token)
            except json.JSONDecodeError:
                return False
        else:
            token = state_token
        return all(k in token for k in ("access_token", "scope", "expires_in", "token_type"))

    @staticmethod
    def _parse_state_token(state_token: str | dict) -> dict:
        if isinstance(state_token, str):
            return json.loads(state_token)
        if isinstance(state_token, dict):
            return state_token
        raise UserException("Invalid state token format")

    # ------------------------------------------------------------------ #
    # Tenant resolution                                                     #
    # ------------------------------------------------------------------ #

    def _resolve_tenant_id(self, explicit_tenant: str = None) -> str:
        if explicit_tenant:
            return explicit_tenant

        try:
            available = self.client.get_available_tenant_ids()
        except XeroException as exc:
            raise UserException(f"Failed to retrieve tenant list: {exc}") from exc

        if not available:
            raise UserException(
                "No Xero tenants accessible with the current credentials. Please check your authorization."
            )
        if len(available) > 1:
            logging.warning(
                f"Multiple tenants available ({available}). "
                f"Using first: {available[0]}. "
                "Set 'tenant_id' in root configuration to be explicit."
            )
        return available[0]

    # ------------------------------------------------------------------ #
    # Input helpers                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _apply_column_mapping(rows: list[dict], mapping: list[ColumnMapping]) -> list[dict]:
        """Rename columns according to mapping and drop unmapped columns."""
        col_map = {cm.source: cm.destination for cm in mapping}
        return [{col_map[k]: v for k, v in row.items() if k in col_map} for row in rows]

    @staticmethod
    def _read_csv(file_path: str) -> list[dict]:
        rows = []
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return rows

    def _write_validation_errors_table(self, errors: list[dict]) -> None:
        component_id = (self.environment_variables.component_id or "keboola.wr-xero-accounting").replace(".", "-")
        destination = f"out.c-{component_id}.validation_errors"
        table_def = self.create_out_table_definition(
            "validation_errors.csv", incremental=False, destination=destination
        )
        with open(table_def.full_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["entity_type", "record_id", "errors"])
            writer.writeheader()
            writer.writerows(errors)
        self.write_manifest(table_def)
        logging.info(f"Validation errors table written with {len(errors)} row(s) to 'validation_errors'")

    # ------------------------------------------------------------------ #
    # Writer factory                                                        #
    # ------------------------------------------------------------------ #

    def _build_writer(self, entity_type: EntityType, write_mode: str, tenant_id: str) -> BaseWriter:
        writer_class = WRITER_MAP.get(entity_type)
        if not writer_class:
            raise UserException(f"Unsupported entity type: '{entity_type.value}'")
        return writer_class(self.client.api_client, tenant_id, write_mode)

    # ------------------------------------------------------------------ #
    # Sync actions                                                          #
    # ------------------------------------------------------------------ #

    @sync_action("loadFieldSuggestions")
    def load_field_suggestions(self):
        """Match input table columns to Xero field names using fuzzy matching.

        For each entity:
        - Looks up the input table columns via Keboola Storage API (using the source_table
          destination name to find the table ID in the storage input mapping)
        - Fuzzy-matches those column names to the known Xero fields for the entity type
        - Preserves any existing column_mapping entries
        Falls back to field-name-only suggestions when the table is not found in storage.
        """
        params = self.configuration.parameters
        entities = params.get("entities", [])

        # Build lookup: destination filename → (table_id, pre-selected columns)
        input_table_map = {t.destination.removesuffix(".csv"): t for t in self.configuration.tables_input_mapping}

        updated_entities = []
        for entity in entities:
            entity_type = entity.get("entity_type", "")
            existing_mapping = entity.get("column_mapping", [])
            suggestions = ENTITY_FIELD_SUGGESTIONS.get(entity_type, [])

            source_key = entity.get("source_table", "").removesuffix(".csv")
            table_def = input_table_map.get(source_key)

            if table_def:
                # Use explicitly selected columns, or fetch all columns from SAPI
                columns = (
                    list(table_def.columns)
                    if table_def.columns
                    else self._get_table_columns_from_sapi(table_def.source)
                )
                required_fields = ENTITY_FIELD_REQUIRED.get(entity_type, set())
                new_mapping = self._build_mapped_columns(columns, suggestions, existing_mapping, required_fields)
            else:
                # No input mapping found — fall back to Xero field list with empty sources
                logging.warning(
                    f"[{entity_type}] Input table '{entity.get('source_table')}' not found in "
                    "storage mapping — falling back to field-name suggestions."
                )
                required_fields = ENTITY_FIELD_REQUIRED.get(entity_type, set())
                existing_by_dest = {m["destination"]: m for m in existing_mapping}
                new_mapping = []
                for field in suggestions:
                    if field in existing_by_dest:
                        new_mapping.append(existing_by_dest[field])
                    else:
                        status = "required" if field in required_fields else "optional"
                        new_mapping.append({"source": "", "destination": field, "required": status})

            updated_entities.append({**entity, "column_mapping": new_mapping})

        return {"type": "data", "data": {"entities": updated_entities}}

    def _get_table_columns_from_sapi(self, table_id: str) -> list[str]:
        """Fetch column names for a Keboola Storage table via the Storage API."""
        url = self.environment_variables.url
        token = self.environment_variables.token
        if not url or not token:
            logging.warning("Missing KBC environment variables — cannot fetch table columns from SAPI")
            return []
        try:
            response = requests.get(
                f"{url}/v2/storage/tables/{table_id}",
                headers={"X-StorageApi-Token": token},
                timeout=30,
            )
            response.raise_for_status()
            return response.json().get("columns", [])
        except Exception as exc:
            logging.warning(f"Could not fetch columns for table '{table_id}' from SAPI: {exc}")
            return []

    @staticmethod
    def _fuzzy_match_field(column: str, xero_fields: list[str]) -> str:
        """Match a source column name to the best Xero field name, or return empty string."""

        def normalize(s: str) -> str:
            return s.lower().replace("_", "").replace("-", "").replace(" ", "")

        # 1. Exact match
        if column in xero_fields:
            return column
        # 2. Case-insensitive exact
        lower_map = {f.lower(): f for f in xero_fields}
        if column.lower() in lower_map:
            return lower_map[column.lower()]
        # 3. Normalized match (strips underscores/hyphens/spaces, lowercased)
        normalized_map = {normalize(f): f for f in xero_fields}
        if normalize(column) in normalized_map:
            return normalized_map[normalize(column)]
        return ""

    @staticmethod
    def _build_mapped_columns(
        columns: list[str],
        suggestions: list[str],
        existing_mapping: list[dict],
        required_fields: set[str],
    ) -> list[dict]:
        """Build column_mapping anchored on the Xero field list.

        For each known Xero field, find the best matching source column via fuzzy matching.
        The result is always ordered by the Xero field list so the destination column is stable.
        Existing entries (keyed by destination) are preserved as-is.
        """
        existing_by_dest = {m["destination"]: m for m in existing_mapping}
        used_sources = {m["source"] for m in existing_mapping if m["source"]}

        # Build mapping: Xero field → first matching source column
        field_to_source: dict[str, str] = {}
        for col in columns:
            if col in used_sources:
                continue
            matched_field = Component._fuzzy_match_field(col, suggestions)
            if matched_field and matched_field not in field_to_source:
                field_to_source[matched_field] = col

        result = []
        for field in suggestions:
            if field in existing_by_dest:
                result.append(existing_by_dest[field])
            else:
                status = "required" if field in required_fields else "optional"
                result.append({"source": field_to_source.get(field, ""), "destination": field, "required": status})

        return result

    @sync_action("listTenants")
    def list_tenants(self):
        """Return available Xero tenants for the dropdown in root config."""
        self._init_client()
        self._save_config_state_via_api()
        try:
            tenants = self.client.get_available_tenants()
        except XeroException as exc:
            raise UserException(f"Failed to list tenants: {exc}") from exc
        return [SelectElement(value=t["id"], label=f"{t['name']} ({t['id']})") for t in tenants]


if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
