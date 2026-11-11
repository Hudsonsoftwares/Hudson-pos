# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayslipInputType(models.Model):
    """Configurable external input types (e.g. Overtime, Bonus, Advance Recovery, Deduction)."""
    _name = 'hr.payslip.input.type'
    _description = 'Payslip Input Type'
    _order = 'sequence, id'

    name = fields.Char(string='Description', required=True, translate=True)
    code = fields.Char(string='Code', required=True, index=True)
    sequence = fields.Integer(string='Sequence', default=10)
    country_id = fields.Many2one('res.country', string='Country')
    input_line_type_ids = fields.Many2many(
        'hr.payroll.structure',
        'hr_payslip_input_type_structure_rel',
        'input_type_id',
        'struct_id',
        string='Availability in Structure'
    )
    struct_ids = fields.Many2many(
        'hr.payroll.structure',
        related='input_line_type_ids',
        string='Availability in Structure',
        readonly=False
    )


class HrPayslipInput(models.Model):
    """External input lines fed into a specific payslip for rule calculation."""
    _name = 'hr.payslip.input'
    _description = 'Payslip Input'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Pay Slip',
        required=True,
        ondelete='cascade',
        index=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='payslip_id.employee_id',
        store=True,
        readonly=True,
        index=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='payslip_id.company_id',
        store=True,
        readonly=True,
        index=True
    )
    sequence = fields.Integer(string='Sequence', default=10, required=True, index=True)
    input_type_id = fields.Many2one(
        'hr.payslip.input.type',
        string='Input Type'
    )
    code = fields.Char(
        string='Code',
        required=True,
        help="Input code that can be referenced in salary rules (e.g. inputs.OVERTIME.amount)"
    )
    amount = fields.Float(
        string='Amount',
        default=0.0,
        help="Amount or monetary value of this input line"
    )
    contract_id = fields.Many2one(
        'hr.version',
        string='Contract',
        help="The contract related to this input"
    )
    adjustment_id = fields.Many2one(
        'hr.salary.adjustment',
        string='Salary Adjustment',
        ondelete='set null',
        index=True,
        help="Source salary adjustment that generated this payslip input."
    )

    @api.onchange('input_type_id')
    def _onchange_input_type_id(self):
        if self.input_type_id:
            self.name = self.input_type_id.name
            self.code = self.input_type_id.code
            if self.input_type_id.sequence:
                self.sequence = self.input_type_id.sequence

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('input_type_id'):
                input_type = self.env['hr.payslip.input.type'].browse(vals['input_type_id'])
                if not vals.get('name') and input_type.exists():
                    vals['name'] = input_type.name
                if not vals.get('code') and input_type.exists():
                    vals['code'] = input_type.code
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('input_type_id'):
            input_type = self.env['hr.payslip.input.type'].browse(vals['input_type_id'])
            if not vals.get('code') and not self.code and input_type.exists():
                vals['code'] = input_type.code
            if not vals.get('name') and not self.name and input_type.exists():
                vals['name'] = input_type.name
        return super().write(vals)
