# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HdsHrSnapshot(models.Model):
    _inherit = 'hds.hr.snapshot'

    snapshot_pf_wage = fields.Monetary(
        string='PF Wage',
        compute='_compute_snapshot_pf_amounts',
        currency_field='currency_id',
        store=True,
        help="PF contribution wage for this snapshot period."
    )
    snapshot_employee_epf = fields.Monetary(
        string='Employee EPF',
        compute='_compute_snapshot_pf_amounts',
        currency_field='currency_id',
        store=True,
        help="Employee EPF deduction."
    )
    snapshot_employer_epf = fields.Monetary(
        string='Employer EPF',
        compute='_compute_snapshot_pf_amounts',
        currency_field='currency_id',
        store=True,
        help="Employer EPF share."
    )
    snapshot_employer_eps = fields.Monetary(
        string='Employer EPS',
        compute='_compute_snapshot_pf_amounts',
        currency_field='currency_id',
        store=True,
        help="Employer EPS share."
    )

    @api.depends('payslip_id', 'payslip_id.line_ids', 'payslip_id.line_ids.total')
    def _compute_snapshot_pf_amounts(self):
        wizard_base = self.env['hds.pf.report.wizard.base']
        for rec in self:
            slip = rec.payslip_id
            if slip:
                pf_vals = wizard_base._get_pf_line_amounts(slip)
                rec.snapshot_pf_wage = pf_vals['pf_wage']
                rec.snapshot_employee_epf = pf_vals['ee_epf']
                rec.snapshot_employer_epf = pf_vals['er_epf']
                rec.snapshot_employer_eps = pf_vals['er_eps']
            else:
                rec.snapshot_pf_wage = 0.0
                rec.snapshot_employee_epf = 0.0
                rec.snapshot_employer_epf = 0.0
                rec.snapshot_employer_eps = 0.0
