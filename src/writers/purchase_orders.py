import logging
from typing import Any, Dict, List, Optional

from xero_python.accounting.models import Contact, LineItem, PurchaseOrder, PurchaseOrders
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter, _is_empty, _to_float


class PurchaseOrdersWriter(BaseWriter):
    """Writes PurchaseOrder records to Xero.

    Supported CSV columns:
      PurchaseOrderID, PurchaseOrderNumber, DateString, DeliveryDateString, Status,
      CurrencyCode, CurrencyRate, Reference, SentToContact, DeliveryAddress,
      AttentionTo, Telephone, DeliveryInstructions, ExpectedArrivalDate,
      Contact_ContactID, Contact_Name,
      LineItem_Description, LineItem_Quantity, LineItem_UnitAmount, LineItem_AccountCode,
      LineItem_TaxType, LineItem_ItemCode, LineItem_LineItemID
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: List[Dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} purchase order(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        pos = [self._row_to_po(row) for row in batch]
        pos_obj = PurchaseOrders(purchase_orders=pos)
        try:
            if self.write_mode == "upsert":
                result = self.accounting_api.update_or_create_purchase_orders(
                    self.tenant_id,
                    pos_obj,
                    summarize_errors=False,
                )
            else:
                result = self.accounting_api.create_purchase_orders(
                    self.tenant_id,
                    pos_obj,
                    summarize_errors=False,
                )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write purchase orders batch: {exc}")
            raise

    def _row_to_po(self, row: Dict[str, Any]) -> PurchaseOrder:
        po = PurchaseOrder()

        if v := self._get(row, "PurchaseOrderID"):
            po.purchase_order_id = v
        if v := self._get(row, "PurchaseOrderNumber"):
            po.purchase_order_number = v
        if v := self._get(row, "DateString"):
            po.date_string = v
        if v := self._get(row, "DeliveryDateString"):
            po.delivery_date_string = v
        if v := self._get(row, "Status"):
            po.status = v
        if v := self._get(row, "CurrencyCode"):
            po.currency_code = v
        if v := self._get(row, "Reference"):
            po.reference = v
        if v := self._get(row, "DeliveryAddress"):
            po.delivery_address = v
        if v := self._get(row, "AttentionTo"):
            po.attention_to = v
        if v := self._get(row, "Telephone"):
            po.telephone = v
        if v := self._get(row, "DeliveryInstructions"):
            po.delivery_instructions = v

        currency_rate = _to_float(row.get("CurrencyRate"))
        if currency_rate is not None:
            po.currency_rate = currency_rate

        contact = self._build_contact(row)
        if contact:
            po.contact = contact

        line_item = self._build_line_item(row)
        if line_item:
            po.line_items = [line_item]

        return po

    @staticmethod
    def _build_contact(row: Dict[str, Any]) -> Optional[Contact]:
        contact_id = row.get("Contact_ContactID")
        contact_name = row.get("Contact_Name")
        if _is_empty(contact_id) and _is_empty(contact_name):
            return None
        contact = Contact()
        if not _is_empty(contact_id):
            contact.contact_id = str(contact_id).strip()
        if not _is_empty(contact_name):
            contact.name = str(contact_name).strip()
        return contact

    @staticmethod
    def _build_line_item(row: Dict[str, Any]) -> Optional[LineItem]:
        description = row.get("LineItem_Description")
        if _is_empty(description):
            return None
        line_item = LineItem(description=str(description).strip())
        if v := row.get("LineItem_Quantity"):
            q = _to_float(v)
            if q is not None:
                line_item.quantity = q
        if v := row.get("LineItem_UnitAmount"):
            a = _to_float(v)
            if a is not None:
                line_item.unit_amount = a
        if v := row.get("LineItem_AccountCode"):
            if not _is_empty(v):
                line_item.account_code = str(v).strip()
        if v := row.get("LineItem_TaxType"):
            if not _is_empty(v):
                line_item.tax_type = str(v).strip()
        if v := row.get("LineItem_ItemCode"):
            if not _is_empty(v):
                line_item.item_code = str(v).strip()
        return line_item

    @staticmethod
    def _log_result(result) -> None:
        if hasattr(result, "purchase_orders") and result.purchase_orders:
            ok = sum(1 for po in result.purchase_orders if not po.has_validation_errors)
            errors = [po for po in result.purchase_orders if po.has_validation_errors]
            logging.info(f"PurchaseOrders batch: {ok} ok, {len(errors)} with validation errors")
            for po in errors:
                logging.warning(f"  PO '{po.purchase_order_number}' validation errors: {po.validation_errors}")
