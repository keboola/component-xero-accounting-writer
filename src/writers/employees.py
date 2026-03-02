import logging
from typing import Any

from xero_python.accounting.models import Employee, Employees
from xero_python.api_client import ApiClient

from .base_writer import BaseWriter


class EmployeesWriter(BaseWriter):
    """Writes Employee records to Xero (basic payrun employees).

    Supported CSV columns:
      EmployeeID, FirstName, LastName, ExternalLink_Url, ExternalLink_Description,
      Status
    """

    def __init__(self, api_client: ApiClient, tenant_id: str, write_mode: str) -> None:
        super().__init__(api_client, tenant_id, write_mode)

    def write(self, rows: list[dict[str, Any]]) -> None:
        logging.info(f"Writing {len(rows)} employee(s) to Xero (mode={self.write_mode})")
        self._process_in_batches(rows, self._write_batch)

    def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        employees = [self._row_to_employee(row) for row in batch]
        employees_obj = Employees(employees=employees)
        try:
            if self.write_mode == "upsert":
                result = self.accounting_api.update_or_create_employees(
                    self.tenant_id,
                    employees_obj,
                )
            else:
                result = self.accounting_api.create_employees(
                    self.tenant_id,
                    employees_obj,
                    summarize_errors=False,
                )
            self._log_result(result)
        except Exception as exc:
            logging.error(f"Failed to write employees batch: {exc}")
            raise

    def _row_to_employee(self, row: dict[str, Any]) -> Employee:
        employee = Employee()

        if v := self._get(row, "EmployeeID"):
            employee.employee_id = v
        if v := self._get(row, "FirstName"):
            employee.first_name = v
        if v := self._get(row, "LastName"):
            employee.last_name = v
        if v := self._get(row, "Status"):
            employee.status = v

        return employee

    @staticmethod
    def _log_result(result) -> None:
        if hasattr(result, "employees") and result.employees:
            logging.info(f"Employees batch: {len(result.employees)} processed")
