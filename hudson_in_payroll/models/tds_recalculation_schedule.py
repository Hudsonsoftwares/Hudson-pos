# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class TdsRecalculationSchedule(models.Model):
    """
    Persisted TDS Recalculation & Monthly Distribution Schedule Model.
    Created ONCE during the January TDS recalculation workflow.
    Stores the exact recalculated annual tax, YTD TDS, remaining liability, and
    fixed monthly distribution allocations for January, February, and March.

    February and March payslip calculations retrieve this persisted schedule
    instead of re-executing full annual TDS recalculation.
    """
    _name = 'tds.recalculation.schedule'
    _description = 'TDS Recalculation & Monthly Distribution Schedule'
    _order = 'recalculation_date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        ondelete='cascade',
        index=True
    )
    financial_year_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        required=True,
        ondelete='cascade',
        index=True
    )
    declaration_id = fields.Many2one(
        'tds.employee.declaration',
        string="Tax Declaration",
        ondelete='set null'
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='company_id.currency_id',
        readonly=True
    )

    recalculation_from_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
    ], string="Recalculation From Month", default='1', required=True)

    distribution_months = fields.Integer(
        string="Distribution Months",
        default=3,
        required=True,
        help="Configured distribution count at recalculation time (fixed at 3 for Jan-Mar)."
    )
    recalculation_date = fields.Date(
        string="Recalculation Date",
        default=fields.Date.today,
        required=True
    )

    recalculated_annual_tax = fields.Monetary(
        string="Recalculated Annual Tax (₹)",
        currency_field='currency_id',
        default=0.0
    )
    ytd_tds_at_recalculation = fields.Monetary(
        string="YTD TDS at Recalculation (₹)",
        currency_field='currency_id',
        default=0.0
    )
    remaining_tax_liability = fields.Monetary(
        string="Remaining Tax Liability (₹)",
        currency_field='currency_id',
        default=0.0
    )

    january_tds = fields.Monetary(
        string="January Allocated TDS (₹)",
        currency_field='currency_id',
        default=0.0
    )
    february_tds = fields.Monetary(
        string="February Allocated TDS (₹)",
        currency_field='currency_id',
        default=0.0
    )
    march_tds = fields.Monetary(
        string="March Allocated TDS (₹)",
        currency_field='currency_id',
        default=0.0
    )

    status = fields.Selection([
        ('draft', 'Draft'),
        ('distribution_active', 'Distribution Active'),
        ('completed', 'Completed')
    ], string="Distribution Status", default='distribution_active', required=True)

    _sql_constraints = [
        ('emp_fy_unique', 'unique(employee_id, financial_year_id)',
         'A TDS Recalculation Schedule already exists for this Employee and Financial Year!')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            _logger.warning("""[TDS_DEBUG_TRACE][SCHEDULE_LIFECYCLE]
schedule_id=%s
operation=CREATE
annual_tax=%s
ytd_tds=%s
remaining_tax=%s
distribution_months=%s
january_tds=%s
february_tds=%s
march_tds=%s
status=%s
source_method=TdsRecalculationSchedule.create
payslip_id=%s
eval_date=%s""",
                rec.id, rec.recalculated_annual_tax, rec.ytd_tds_at_recalculation,
                rec.remaining_tax_liability, rec.distribution_months, rec.january_tds,
                rec.february_tds, rec.march_tds, rec.status,
                self.env.context.get('active_id', 'N/A'), rec.recalculation_date
            )
        return records

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            _logger.warning("""[TDS_DEBUG_TRACE][SCHEDULE_LIFECYCLE]
schedule_id=%s
operation=WRITE
annual_tax=%s
ytd_tds=%s
remaining_tax=%s
distribution_months=%s
january_tds=%s
february_tds=%s
march_tds=%s
status=%s
source_method=TdsRecalculationSchedule.write
payslip_id=%s
eval_date=%s""",
                rec.id, rec.recalculated_annual_tax, rec.ytd_tds_at_recalculation,
                rec.remaining_tax_liability, rec.distribution_months, rec.january_tds,
                rec.february_tds, rec.march_tds, rec.status,
                self.env.context.get('active_id', 'N/A'), rec.recalculation_date
            )
        return res
