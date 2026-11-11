# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HrSalaryAdjustmentWizard(models.TransientModel):
    """
    Wizard to generate multiple salary adjustment records across multiple employees in batch.
    Matches the Odoo Online 'Generate Multiple Payslip Adjustments' dialog.
    """
    _name = 'hr.salary.adjustment.wizard'
    _description = 'Generate Multiple Salary Adjustments'

    employee_ids = fields.Many2many(
        'hr.employee',
        'hr_salary_adj_wizard_employee_rel',
        'wizard_id',
        'employee_id',
        string='Employees',
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Select one or more employees to receive this salary adjustment."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True
    )
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        related='company_id.country_id',
        store=True,
        readonly=True,
    )
    input_type_id = fields.Many2one(
        'hr.payslip.input.type',
        string='Salary Rule',
        required=True,
        domain="['|', ('country_id', '=', False), ('country_id', '=', country_id)]",
        help="Other Input Type linked to this adjustment (global and country-specific)."
    )
    amount = fields.Monetary(
        string='Payslip Amount',
        required=True,
        currency_field='currency_id',
        help="Amount to be applied per payslip."
    )
    negative = fields.Boolean(
        string='Negative Value',
        default=False,
        help="If checked, the adjustment will be registered as negative."
    )
    repeat = fields.Boolean(
        string='Repeat',
        default=False,
        help="Apply this adjustment on every payslip until the End Date, "
             "or until the end of the employee's contract if no End Date is set."
    )
    duration = fields.Selection([
        ('one_time', 'One Time'),
        ('limited', 'Limited'),
        ('unlimited', 'Unlimited'),
    ], string='Duration', compute='_compute_duration', store=True)

    date_start = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.today
    )
    date_end = fields.Date(
        string='End Date',
        help="Last date the adjustment repeats. Leave empty to repeat until the end of the employee's contract."
    )
    until_amount = fields.Monetary(
        string='Until Amount',
        currency_field='currency_id',
        help="Optional total cap amount."
    )
    note = fields.Char(
        string='Note',
        help="Description or memo for the adjustments."
    )
    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Pay Run',
        help="Pay run this adjustment was created from."
    )
    employee_wizard_id = fields.Many2one(
        'hr.payslip.employees',
        string='Select Employees Wizard',
        help="Select Employees dialog that opened this wizard; payslips are generated through it on Create."
    )

    @api.depends('repeat', 'date_end')
    def _compute_duration(self):
        for wiz in self:
            if not wiz.repeat:
                wiz.duration = 'one_time'
            elif wiz.date_end:
                wiz.duration = 'limited'
            else:
                wiz.duration = 'unlimited'

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id and self.employee_ids:
            self.employee_ids = self.employee_ids.filtered(
                lambda e: not e.company_id or e.company_id == self.company_id
            )

    @api.onchange('employee_ids')
    def _onchange_employee_ids(self):
        if self.employee_ids and not self.company_id:
            if self.employee_ids[0].company_id:
                self.company_id = self.employee_ids[0].company_id

    @api.constrains('date_start', 'date_end', 'repeat')
    def _check_dates(self):
        for wiz in self:
            if wiz.repeat and wiz.date_end and wiz.date_end < wiz.date_start:
                raise ValidationError(_("End Date cannot be before Start Date."))

    @api.constrains('amount')
    def _check_amount(self):
        for wiz in self:
            if wiz.amount <= 0.0:
                raise ValidationError(_("Amount must be strictly greater than 0.0."))

    def action_create_adjustments(self):
        self.ensure_one()
        if not self.employee_ids:
            raise UserError(_("Please select at least one employee."))

        # Enforce strict multi-company isolation
        invalid_emps = self.employee_ids.filtered(
            lambda e: e.company_id and e.company_id != self.company_id
        )
        if invalid_emps:
            raise UserError(_(
                "The following employees do not belong to the selected company '%(company)s':\n%(employees)s"
            ) % {
                'company': self.company_id.name,
                'employees': '\n'.join(f"• {e.name} ({e.company_id.name})" for e in invalid_emps),
            })

        created_adjustments = self.env['hr.salary.adjustment']
        AdjModel = self.env['hr.salary.adjustment']
        for emp in self.employee_ids:
            emp_bank = AdjModel._get_employee_bank_account(emp)
            vals = {
                'employee_id': emp.id,
                'company_id': emp.company_id.id or self.company_id.id,
                'input_type_id': self.input_type_id.id,
                'amount': self.amount,
                'negative': self.negative,
                'duration': self.duration,
                'date_start': self.date_start,
                'date_end': self.date_end if self.duration == 'limited' else False,
                'until_amount': self.until_amount if self.duration == 'limited' else 0.0,
                'beneficiary_bank_id': emp_bank.id if emp_bank else False,
                'note': self.note,
                'state': 'running',
            }
            created_adjustments |= AdjModel.create(vals)

        run = self.payslip_run_id
        if run and self.employee_wizard_id:
            # Opened from 'Select Employees': generate payslips for the ticked employees.
            # New payslips pick up the adjustments through _populate_inputs().
            return self.employee_wizard_id.with_context(
                active_model='hr.payslip.run',
                active_id=run.id,
            ).action_select()

        if run:
            # Existing draft payslips were already re-synced by hr.salary.adjustment.create()
            run._compute_financial_totals()
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'hr.payslip.run',
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_id': run.id,
                'target': 'current',
            }

        action = {
            'name': _('Salary Adjustments'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.salary.adjustment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_adjustments.ids)],
            'target': 'current',
        }
        if len(created_adjustments) == 1:
            action['res_id'] = created_adjustments.id
            action['view_mode'] = 'form'
        return action
