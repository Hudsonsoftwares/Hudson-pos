# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FinalSettlementLine(models.Model):
    """
    Reusable Breakdown Line Model for Employee Final Settlement.
    Represents individual earnings and deductions (e.g. Leave Encashment, Gratuity, PF, Notice Pay, Recovery)
    forming the overall final settlement statement.
    """
    _name = 'final.settlement.line'
    _description = 'Final Settlement Breakdown Line'
    _order = 'line_type asc, sequence asc, id asc'

    sequence = fields.Integer(string="Sequence", default=10)
    settlement_id = fields.Many2one(
        'final.settlement',
        string="Final Settlement",
        required=True,
        ondelete='cascade',
        index=True
    )

    # Related Fields (DRY: Company, Employee, Currency derived from Parent Settlement)
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        related='settlement_id.company_id',
        store=True,
        readonly=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        related='settlement_id.employee_id',
        store=True,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='settlement_id.currency_id',
        store=True,
        readonly=True
    )

    # Component Identification
    component_code = fields.Char(
        string="Component Code",
        required=True,
        index=True,
        help="Code identifier for the settlement component (e.g. LEAVE_ENCASH, GRATUITY, PF, NOTICE_PAY)."
    )
    component_name = fields.Char(
        string="Component Name",
        required=True,
        help="Display name of the component (e.g. Leave Encashment, Gratuity, Notice Pay)."
    )
    description = fields.Text(
        string="Description",
        help="Detailed notes or computation breakdown of this component line."
    )

    # Amount & Line Type
    line_type = fields.Selection([
        ('earning', 'Earning'),
        ('deduction', 'Deduction'),
    ], string="Line Type", default='earning', required=True, help="Classification of this line as an Earning or Deduction.")

    amount = fields.Monetary(
        string="Amount",
        currency_field='currency_id',
        default=0.0,
        required=True,
        help="Monetary value of this settlement line."
    )

    @api.constrains('amount', 'line_type')
    def _check_valid_line_amount_and_type(self):
        for record in self:
            if record.line_type not in ('earning', 'deduction'):
                raise ValidationError(_("Line type must be 'earning' or 'deduction'."))
            if record.amount < 0.0:
                raise ValidationError(_("Settlement line amount cannot be negative (%s).") % record.amount)
