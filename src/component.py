import csv
import json
import logging
from typing import Dict, List, Union

from keboola.component.base import ComponentBase, sync_action
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement

from client import XeroClient, XeroException
from configuration import EntityType, RootConfiguration, RowConfiguration
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

WRITER_MAP: Dict[EntityType, type] = {
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

        row_config = RowConfiguration(**self.configuration.parameters)
        entity_type = row_config.entity_type
        write_mode = row_config.write_mode.value
        tenant_id = self._resolve_tenant_id()

        input_tables = self.get_input_tables_definitions()
        if not input_tables:
            raise UserException("No input table configured. Please add an input table mapping in the configuration.")

        rows = self._read_csv(input_tables[0].full_path)
        logging.info(f"Loaded {len(rows)} row(s) from input table")

        writer = self._build_writer(entity_type, write_mode, tenant_id)
        writer.write(rows)

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

    def _init_client_from_state(self, state_token: Union[str, Dict]) -> None:
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
    def _parse_state_token(state_token: Union[str, Dict]) -> Dict:
        if isinstance(state_token, str):
            return json.loads(state_token)
        if isinstance(state_token, dict):
            return state_token
        raise UserException("Invalid state token format")

    # ------------------------------------------------------------------ #
    # Tenant resolution                                                     #
    # ------------------------------------------------------------------ #

    def _resolve_tenant_id(self) -> str:
        root_config = RootConfiguration(**self.configuration.parameters)
        explicit_tenant = root_config.tenant_id
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
    def _read_csv(file_path: str) -> List[Dict]:
        rows = []
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return rows

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
        try:
            tenant_ids = self.client.get_available_tenant_ids()
        except XeroException as exc:
            raise UserException(f"Failed to list tenants: {exc}") from exc
        return [SelectElement(t, t) for t in tenant_ids]


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
