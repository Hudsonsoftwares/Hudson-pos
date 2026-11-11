# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipRunDuplicateWizard(models.TransientModel):
    """Wizard to display duplicate payslips warning popup when validating or processing a pay run."""
    _name = 'hr.payslip.run.duplicate.wizard'
    _description = 'Pay Run Duplicate Payslips Warning'

    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Pay Run Batch',
        required=True,
        readonly=True,
    )
    duplicate_slip_ids = fields.Many2many(
        'hr.payslip',
        string='Duplicate Payslips',
        readonly=True,
    )
    duplicate_count = fields.Integer(
        string='Duplicate Count',
        compute='_compute_details',
    )
    duplicate_employee_names = fields.Char(
        string='Duplicate Employees',
        compute='_compute_details',
    )

    @api.depends('duplicate_slip_ids')
    def _compute_details(self):
        for wiz in self:
            wiz.duplicate_count = len(wiz.duplicate_slip_ids)
            emp_names = list(dict.fromkeys(wiz.duplicate_slip_ids.mapped('employee_id.name')))
            wiz.duplicate_employee_names = ", ".join(emp_names)

    def action_proceed_validate(self):
        """Proceed with batch validation anyway, bypassing duplicate check."""
        self.ensure_one()
        res = self.payslip_run_id.with_context(skip_duplicate_check=True).action_batch_validate()
        # Pass on the "could not validate" warning, if any
        return res if isinstance(res, dict) else {'type': 'ir.actions.act_window_close'}

    def action_remove_and_validate(self):
        """Remove duplicate payslips from batch, then validate the remaining valid payslips."""
        self.ensure_one()
        run = self.payslip_run_id
        if run.state != 'draft':
            raise UserError(_("You can only remove duplicate payslips when the pay run is in Draft state."))
        if self.duplicate_slip_ids:
            self.duplicate_slip_ids.unlink()
            run._compute_counts()
            run._compute_financial_totals()
            run._compute_milestones()
        res = run.with_context(skip_duplicate_check=True).action_batch_validate()
        # Pass on the "could not validate" warning, if any
        return res if isinstance(res, dict) else {'type': 'ir.actions.act_window_close'}
