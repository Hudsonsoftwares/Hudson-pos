# -*- coding: utf-8 -*-
import logging

from odoo import fields
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError
from ..base import BaseStatutoryService
from .salary_preview_service import SalaryPreviewService
from .payroll_refresh_service import PayrollRefreshService
from .statutory_refresh_service import StatutoryRefreshService
from ..audit.audit_service import StatutoryAuditSession

_logger = logging.getLogger(__name__)


class SalaryRevisionService(BaseStatutoryService):
    """
    Central Facade for Salary Revisions.
    Validates revision criteria, creates immutable historical revision records, updates active contracts,
    delegates statutory refreshes, and creates audit trail records.
    """

    def __init__(self, env):
        super().__init__(env)
        self.preview_service = SalaryPreviewService(env)
        self.payroll_refresh = PayrollRefreshService(env)
        self.statutory_refresh = StatutoryRefreshService(env)

    def execute_salary_revision(self, wizard):
        """
        Executes confirmed salary revision from wizard data.
        """
        employee = wizard.employee_id
        effective_date = wizard.effective_date
        self._check_effective_date(effective_date)

        # The revision starts from the version in force on its effective date
        contract = (employee._get_version(effective_date) if hasattr(employee, '_get_version') else False) \
            or wizard.contract_id or self._get_active_contract(employee)

        if not contract:
            raise UserError(self.env._("No active contract found for employee '%s'. Revisions require an active contract.") % employee.name)

        c_start = getattr(contract, 'contract_date_start', False) or getattr(contract, 'date_start', False)
        if c_start and effective_date < c_start:
            raise ValidationError(self.env._("Revision effective date (%s) cannot precede contract start date (%s).") % (effective_date, c_start))

        current_wage = contract.wage or 0.0
        new_wage = wizard.revised_wage

        if new_wage <= 0.0:
            raise ValidationError(self.env._("Revised gross wage must be greater than zero."))

        # Check for duplicate revision on same effective date
        existing = self.env['hds.in.salary.revision'].search([
            ('employee_id', '=', employee.id),
            ('effective_date', '=', effective_date),
            ('state', '=', 'approved')
        ], limit=1)
        if existing:
            raise ValidationError(self.env._("A confirmed salary revision already exists for employee '%s' on effective date %s.") % (employee.name, effective_date))

        # 1. Preview Impact
        preview = self.preview_service.calculate_preview(employee, current_wage, new_wage, effective_date=effective_date)

        # 2. Create Immutable Salary Revision Record
        revision_vals = {
            'employee_id': employee.id,
            'contract_id': contract.id,
            'effective_date': effective_date,
            'revision_type': wizard.revision_type,
            'revision_basis': wizard.revision_basis,
            'capped_wage_amount': wizard.capped_wage_amount,
            'computation_type': wizard.computation_type,
            'increase_percentage': wizard.increase_percentage,
            'increase_amount': wizard.increase_amount,
            'extra_amount': getattr(wizard, 'extra_amount', 0.0) or 0.0,
            'old_wage': current_wage,
            'new_wage': new_wage,
            'wage_difference': preview['wage_difference'],
            'old_employer_cost_monthly': preview['old_ctc'],
            'new_employer_cost_monthly': preview['new_ctc'],
            'old_epf_wage': preview['old_epf_wage'],
            'new_epf_wage': preview['new_epf_wage'],
            'old_employee_epf': preview['old_ee_epf'],
            'new_employee_epf': preview['new_ee_epf'],
            'old_employer_pf': preview['old_er_pf'],
            'new_employer_pf': preview['new_er_pf'],
            'old_esic_applicable': preview['old_esic_app'],
            'new_esic_applicable': preview['new_esic_app'],
            'old_employee_esic': preview['old_ee_esic'],
            'new_employee_esic': preview['new_ee_esic'],
            'old_employer_esic': preview['old_er_esic'],
            'new_employer_esic': preview['new_er_esic'],
            'old_pt_amount': preview.get('old_pt_amount', 0.0),
            'new_pt_amount': preview.get('new_pt_amount', preview.get('pt_amount', 0.0)),
            'old_lwf_amount': preview.get('old_lwf_amount', 0.0),
            'new_lwf_amount': preview.get('new_lwf_amount', preview.get('lwf_amount', 0.0)),
            'reason': wizard.reason,
            'notes': wizard.notes,
            'state': 'approved',
            'created_by_id': self.env.uid,
        }
        # 3. New employee version from the effective date (the employee's version history), carrying the
        # new wage; earlier versions keep the old salary
        new_version = self._create_revision_version(employee, contract, effective_date)
        revision_vals['contract_id'] = new_version.id
        revision_record = self.env['hds.in.salary.revision'].create(revision_vals)

        mode = getattr(wizard, 'breakdown_distribution_mode', 'auto_structure')
        manual_dict = wizard._get_manual_breakdown_dict() if hasattr(wizard, '_get_manual_breakdown_dict') and mode in ('manual_adjust', 'copy_current') else None
        self.payroll_refresh.refresh_contract_payroll(
            new_version, new_wage, effective_date=effective_date, mode=mode, manual_dict=manual_dict
        )

        # 4. Refresh Statutory Components
        self.statutory_refresh.refresh_statutory_components(employee, new_wage, effective_date=effective_date)

        # 5. Audit Logging
        payslip_dummy = self.env['hr.payslip'].search([('employee_id', '=', employee.id)], limit=1)
        if not payslip_dummy:
            class DummyPayslip:
                def __init__(self, emp):
                    self.employee_id = emp
                    self.company_id = emp.company_id or emp.env.company
                    self.id = False
                    self.date_to = effective_date or fields.Date.today()
            payslip_dummy = DummyPayslip(employee)

        with StatutoryAuditSession(self.env, payslip_dummy, statutory_module='revision', rule_code='SALARY_REVISION') as audit:
            audit.attach_input('wage', current_wage)
            audit.attach_output('wage', new_wage)
            if hasattr(wizard, 'current_basic') and hasattr(wizard, 'new_basic') and wizard.current_basic != wizard.new_basic:
                audit.attach_input('basic_salary', wizard.current_basic)
                audit.attach_output('basic_salary', wizard.new_basic)
            if hasattr(wizard, 'current_hra') and hasattr(wizard, 'new_hra') and wizard.current_hra != wizard.new_hra:
                audit.attach_input('hra', wizard.current_hra)
                audit.attach_output('hra', wizard.new_hra)
            if hasattr(wizard, 'current_fixed_allowance') and hasattr(wizard, 'new_fixed_allowance') and wizard.current_fixed_allowance != wizard.new_fixed_allowance:
                audit.attach_input('fixed_allowance', wizard.current_fixed_allowance)
                audit.attach_output('fixed_allowance', wizard.new_fixed_allowance)
            if preview.get('old_ee_epf') is not None and preview.get('new_ee_epf') is not None:
                audit.attach_input('employee_epf', preview.get('old_ee_epf', 0.0))
                audit.attach_output('employee_epf', preview.get('new_ee_epf', 0.0))
            if preview.get('old_er_pf') is not None and preview.get('new_er_pf') is not None:
                audit.attach_input('employer_epf', preview.get('old_er_pf', 0.0))
                audit.attach_output('employer_epf', preview.get('new_er_pf', 0.0))
            if preview.get('old_ee_esic') is not None and preview.get('new_ee_esic') is not None:
                audit.attach_input('employee_esic', preview.get('old_ee_esic', 0.0))
                audit.attach_output('employee_esic', preview.get('new_ee_esic', 0.0))
            if preview.get('old_er_esic') is not None and preview.get('new_er_esic') is not None:
                audit.attach_input('employer_esic', preview.get('old_er_esic', 0.0))
                audit.attach_output('employer_esic', preview.get('new_er_esic', 0.0))
            if preview.get('old_pt_amount') is not None and preview.get('new_pt_amount') is not None:
                audit.attach_input('pt_deduction', preview.get('old_pt_amount', 0.0))
                audit.attach_output('pt_deduction', preview.get('new_pt_amount', 0.0))
            audit.attach_parameter('REVISION_TYPE', wizard.revision_type)
            audit.attach_parameter('REVISION_BASIS', wizard.revision_basis)
            audit.attach_output('revision_record_id', revision_record.id)

        _logger.info(
            "[SalaryRevisionService] Executed salary revision %s for Employee %s: Gross %s -> %s",
            revision_record.name, employee.name, current_wage, new_wage
        )

        return revision_record

    def _check_effective_date(self, effective_date):
        """A salary revision starts on the 1st of a month, today or later."""
        if not effective_date:
            raise ValidationError(self.env._("Set the effective date of the salary revision."))
        today = fields.Date.context_today(self.env.user)
        if effective_date < today:
            raise ValidationError(self.env._(
                "The effective date (%(date)s) is in the past. A salary revision applies from today or a later date.",
                date=effective_date))
        if effective_date.day != 1:
            raise ValidationError(self.env._(
                "The effective date (%(date)s) must be the 1st of a month: payslips are monthly and a revision "
                "applies to whole months.", date=effective_date))

    def _create_revision_version(self, employee, base_version, effective_date):
        """Employee version from the effective date (Odoo's version history): a copy of the version in
        force on that date, or that version itself when it already starts on this date."""
        if not hasattr(employee, 'create_version'):
            return base_version
        new_version = employee.sudo().create_version({'date_version': effective_date})
        # Copying a version must not turn the shortage rate into a manual one (it follows the wage)
        if new_version != base_version and 'shortage_rate_manually_set' in new_version._fields:
            new_version.sudo().write({'shortage_rate_manually_set': base_version.shortage_rate_manually_set})
        return new_version.sudo(False)

    def _get_active_contract(self, employee):
        if not employee:
            return False
        contract = getattr(employee, 'version_id', False) or getattr(employee, 'contract_id', False)
        if contract:
            return contract
        contracts = self.env['hr.version'].search([('employee_id', '=', employee.id)])
        if contracts:
            open_contracts = contracts.filtered(lambda c: getattr(c, 'state', False) == 'open')
            target_list = open_contracts if open_contracts else contracts
            def _sort_key(c):
                start = getattr(c, 'contract_date_start', False) or getattr(c, 'date_start', False)
                return start or fields.Date.today()
            return target_list.sorted(_sort_key, reverse=True)[0]
        return False
