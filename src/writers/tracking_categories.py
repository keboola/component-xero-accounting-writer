import logging
from typing import Any, Dict, List

from xero_python.accounting.models import TrackingCategory
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter


class TrackingCategoriesWriter(BaseWriter):
    """Writes TrackingCategory records to Xero.

    Supported CSV columns:
      TrackingCategoryID, Name, Status
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: List[Dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} tracking category/categories to Xero (mode={self.write_mode})")
        # Tracking categories are written one by one (no batch endpoint)
        for row in rows:
            self._write_single(row)

    def _write_single(self, row: Dict[str, Any]) -> None:
        category = self._row_to_tracking_category(row)
        if not category.name:
            logging.warning("Skipping tracking category row with no Name")
            return
        try:
            if self.write_mode == "upsert" and category.tracking_category_id:
                self.accounting_api.update_tracking_category(
                    self.tenant_id,
                    category.tracking_category_id,
                    category,
                )
                logging.info(f"Updated tracking category '{category.name}'")
            else:
                self.accounting_api.create_tracking_category(
                    self.tenant_id,
                    category,
                )
                logging.info(f"Created tracking category '{category.name}'")
        except Exception as exc:
            logging.error(f"Failed to write tracking category '{category.name}': {exc}")
            raise

    def _row_to_tracking_category(self, row: Dict[str, Any]) -> TrackingCategory:
        category = TrackingCategory()
        if v := self._get(row, "TrackingCategoryID"):
            category.tracking_category_id = v
        if v := self._get(row, "Name"):
            category.name = v
        if v := self._get(row, "Status"):
            category.status = v
        return category
