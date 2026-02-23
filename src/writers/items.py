import logging
from typing import Any, Dict, List

from xero_python.accounting.models import Item, Items, Purchase
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty, _to_bool, _to_float


class ItemsWriter(BaseWriter):
    """Writes Item (product/service catalog) records to Xero.

    Supported CSV columns:
      ItemID, Code, Name, Description, PurchaseDescription, IsSold, IsPurchased,
      PurchaseDetails_UnitPrice, PurchaseDetails_AccountCode, PurchaseDetails_TaxType,
      SalesDetails_UnitPrice, SalesDetails_AccountCode, SalesDetails_TaxType
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: List[Dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} item(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        items = [self._row_to_item(row) for row in batch]
        items_obj = Items(items=items)
        try:
            if self.write_mode == "upsert":
                result = self.accounting_api.update_or_create_items(
                    self.tenant_id,
                    items_obj,
                    summarize_errors=False,
                )
            else:
                result = self.accounting_api.create_items(
                    self.tenant_id,
                    items_obj,
                    summarize_errors=False,
                )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write items batch: {exc}")
            raise

    def _row_to_item(self, row: Dict[str, Any]) -> Item:
        item = Item()

        if v := self._get(row, "ItemID"):
            item.item_id = v
        if v := self._get(row, "Code"):
            item.code = v
        if v := self._get(row, "Name"):
            item.name = v
        if v := self._get(row, "Description"):
            item.description = v
        if v := self._get(row, "PurchaseDescription"):
            item.purchase_description = v

        is_sold = _to_bool(row.get("IsSold"))
        if is_sold is not None:
            item.is_sold = is_sold

        is_purchased = _to_bool(row.get("IsPurchased"))
        if is_purchased is not None:
            item.is_purchased = is_purchased

        purchase_details = self._build_purchase_details(row)
        if purchase_details:
            item.purchase_details = purchase_details

        sales_details = self._build_sales_details(row)
        if sales_details:
            item.sales_details = sales_details

        return item

    @staticmethod
    def _build_purchase_details(row: Dict[str, Any]):
        unit_price = _to_float(row.get("PurchaseDetails_UnitPrice"))
        account_code = row.get("PurchaseDetails_AccountCode")
        if unit_price is None and _is_empty(account_code):
            return None
        purchase = Purchase()
        if unit_price is not None:
            purchase.unit_price = unit_price
        if not _is_empty(account_code):
            purchase.account_code = str(account_code).strip()
        if v := row.get("PurchaseDetails_TaxType"):
            if not _is_empty(v):
                purchase.tax_type = str(v).strip()
        return purchase

    @staticmethod
    def _build_sales_details(row: Dict[str, Any]):
        unit_price = _to_float(row.get("SalesDetails_UnitPrice"))
        account_code = row.get("SalesDetails_AccountCode")
        if unit_price is None and _is_empty(account_code):
            return None
        # xero_python uses the Purchase model for both purchase_details and sales_details
        sales = Purchase()
        if unit_price is not None:
            sales.unit_price = unit_price
        if not _is_empty(account_code):
            sales.account_code = str(account_code).strip()
        if v := row.get("SalesDetails_TaxType"):
            if not _is_empty(v):
                sales.tax_type = str(v).strip()
        return sales

    @staticmethod
    def _log_result(result) -> None:
        if hasattr(result, "items") and result.items:
            ok = sum(1 for it in result.items if not it.has_validation_errors)
            errors = [it for it in result.items if it.has_validation_errors]
            logging.info(f"Items batch: {ok} ok, {len(errors)} with validation errors")
            for it in errors:
                logging.warning(f"  Item '{it.code}' validation errors: {it.validation_errors}")
