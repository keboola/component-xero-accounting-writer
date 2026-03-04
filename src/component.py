import csv
import json
import logging
import os

import requests
from keboola.component.base import ComponentBase, sync_action
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement

from client import XeroClient, XeroException
from configuration import EntityType, RootConfiguration
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

            writer = self._build_writer(entity_cfg.entity_type, entity_cfg.write_mode.value, tenant_id)
            writer.write(rows)
            all_validation_errors.extend(writer.collected_errors)

        if all_validation_errors:
            if root_config.create_errors_table:
                self._write_validation_errors_table(all_validation_errors)
            if not root_config.skip_validation_errors:
                raise UserException(
                    f"Validation errors occurred in {len(all_validation_errors)} record(s). "
                    "Check the job logs for details or enable 'Create Errors Table' to export them."
                )

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
    def _read_csv(file_path: str) -> list[dict]:
        rows = []
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return rows

    def _write_validation_errors_table(self, errors: list[dict]) -> None:
        out_path = os.path.join(self.tables_out_path, "validation_errors.csv")
        os.makedirs(self.tables_out_path, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["entity_type", "record_id", "errors"])
            writer.writeheader()
            writer.writerows(errors)
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
