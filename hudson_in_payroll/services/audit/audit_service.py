# -*- coding: utf-8 -*-
import json
import time
import traceback
# pyrefly: ignore [missing-import]
from odoo import fields


class StatutoryAuditSession:
    """
    Decoupled Context Manager Engine for Statutory Audit Logging.
    Handles zero-overhead toggle checks, timer metrics, JSON serialization,
    and stack trace capture on exception without swallowing errors.
    """

    def __init__(self, env, payslip, statutory_module, rule_code, calculation_type="statutory_compute"):
        self.env = env
        self.payslip = payslip
        self.statutory_module = statutory_module
        self.rule_code = rule_code
        self.calculation_type = calculation_type

        self.inputs = {}
        self.outputs = {}
        self.parameters = {}
        self.messages = []
        self.warnings = []
        self.status = 'success'
        self.start_time = None
        self.enabled = False

    def __enter__(self):
        if self.env.context.get('no_statutory_audit'):
            self.enabled = False
            return self
        company = (self.payslip.company_id if self.payslip and hasattr(self.payslip, 'company_id') else None) or self.env.company
        self.enabled = bool(not company or getattr(company, 'hds_in_enable_statutory_audit', True))
        if self.enabled:
            self.start_time = time.time()
        return self

    def attach_input(self, key, value):
        if self.enabled:
            self.inputs[key] = self._serialize(value)

    def attach_output(self, key, value):
        if self.enabled:
            self.outputs[key] = self._serialize(value)

    def attach_parameter(self, code, value):
        if self.enabled:
            self.parameters[code] = self._serialize(value)

    def log_warning(self, msg):
        if self.enabled:
            self.warnings.append(str(msg))
            if self.status != 'error':
                self.status = 'warning'

    def log_message(self, msg):
        if self.enabled:
            self.messages.append(str(msg))

    def _serialize(self, val):
        if isinstance(val, (int, float, bool, str, type(None))):
            return val
        if hasattr(val, 'isoformat'):
            return val.isoformat()
        return str(val)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.enabled:
            return False  # Always re-raise any exception

        execution_time_ms = (time.time() - self.start_time) * 1000.0 if self.start_time else 0.0
        exception_trace = None

        if exc_type is not None:
            self.status = 'error'
            exception_trace = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            self.messages.append(f"Calculation Error: {str(exc_val)}")

        # Create audit record in database
        employee_id = self.payslip.employee_id.id if self.payslip and hasattr(self.payslip, 'employee_id') and self.payslip.employee_id else False
        company_id = self.payslip.company_id.id if self.payslip and hasattr(self.payslip, 'company_id') and self.payslip.company_id else self.env.company.id
        payslip_id = self.payslip.id if self.payslip and hasattr(self.payslip, 'id') else False
        calc_date = (self.payslip.date_to if self.payslip and hasattr(self.payslip, 'date_to') and self.payslip.date_to else None) or fields.Date.today()

        if employee_id:
            self.env['hds.in.payroll.audit'].sudo().create({
                'company_id': company_id,
                'employee_id': employee_id,
                'payslip_id': payslip_id,
                'user_id': self.env.uid,
                'statutory_module': self.statutory_module,
                'calculation_type': self.calculation_type,
                'rule_code': self.rule_code,
                'calculation_date': calc_date,
                'inputs_json': json.dumps(self.inputs, indent=2, default=str),
                'outputs_json': json.dumps(self.outputs, indent=2, default=str),
                'parameters_json': json.dumps(self.parameters, indent=2, default=str),
                'messages': "\n".join(self.messages) if self.messages else False,
                'warnings': "\n".join(self.warnings) if self.warnings else False,
                'exception_trace': exception_trace,
                'execution_time_ms': round(execution_time_ms, 3),
                'version': '19.0.1.0.0',
                'status': self.status,
            })

        return False  # Never suppress original exception
