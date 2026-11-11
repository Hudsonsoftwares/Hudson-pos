# -*- coding: utf-8 -*-
import calendar
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

MONTH_SELECTION = [
    ('1', 'January'),
    ('2', 'February'),
    ('3', 'March'),
    ('4', 'April'),
    ('5', 'May'),
    ('6', 'June'),
    ('7', 'July'),
    ('8', 'August'),
    ('9', 'September'),
    ('10', 'October'),
    ('11', 'November'),
    ('12', 'December'),
]

MONTH_NAMES = dict(MONTH_SELECTION)


class EsicContributionPeriod(models.Model):
    """
    Master Configuration Model for ESIC Contribution Periods.
    Directly configures the statutory 6-month contribution periods under
    Regulation 31 of the ESI (General) Regulations, 1950.
    """
    _name = 'esic.contribution.period'
    _description = 'ESIC Contribution Period'
    _order = 'company_id, id desc'

    def _auto_init(self):
        """
        Ensure authoritative Indian statutory ESIC contribution periods are global (company_id = NULL)
        so they are automatically visible and usable across all companies nationwide.
        """
        res = super()._auto_init()
        cr = self.env.cr
        try:
            cr.execute("""
                UPDATE esic_contribution_period
                SET company_id = NULL
                WHERE id IN (
                    SELECT res_id FROM ir_model_data
                    WHERE model = 'esic.contribution.period'
                      AND module = 'hudson_in_payroll'
                );
            """)
        except Exception:
            pass
        return res

    name = fields.Char(
        string="Period Name",
        compute="_compute_name",
        store=True,
        readonly=False,
        help="Descriptive name for this ESIC contribution period schedule."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company Scope",
        default=False,
        help="Applicable company. If empty, applies globally as a default."
    )

    period1_start_month = fields.Selection(
        MONTH_SELECTION,
        string="Period 1 Start Month",
        required=True,
        help="Starting month of the first 6-month contribution period."
    )
    period1_end_month = fields.Selection(
        MONTH_SELECTION,
        string="Period 1 End Month",
        required=True,
        help="Ending month of the first 6-month contribution period."
    )
    period2_start_month = fields.Selection(
        MONTH_SELECTION,
        string="Period 2 Start Month",
        required=True,
        help="Starting month of the second 6-month contribution period."
    )
    period2_end_month = fields.Selection(
        MONTH_SELECTION,
        string="Period 2 End Month",
        required=True,
        help="Ending month of the second 6-month contribution period."
    )

    date_from = fields.Date(
        string="Effective From",
        help="Start of date range when this schedule is active. Leave blank for indefinite."
    )
    date_to = fields.Date(
        string="Effective To",
        help="End of date range when this schedule is active. Leave blank for indefinite."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to archive this contribution period configuration."
    )
    summary = fields.Char(
        string="Periods Summary",
        compute="_compute_summary",
        help="Quick summary of the two 6-month contribution periods."
    )
    description = fields.Text(
        string="Remarks",
        help="Statutory notes, notifications, or internal remarks."
    )

    @api.depends('company_id', 'period1_start_month', 'period1_end_month',
                 'period2_start_month', 'period2_end_month')
    def _compute_name(self):
        for rec in self:
            m1_s = MONTH_NAMES.get(rec.period1_start_month, '')
            m1_e = MONTH_NAMES.get(rec.period1_end_month, '')
            m2_s = MONTH_NAMES.get(rec.period2_start_month, '')
            m2_e = MONTH_NAMES.get(rec.period2_end_month, '')

            if m1_s and m1_e and m2_s and m2_e:
                label = f"{m1_s}–{m1_e} & {m2_s}–{m2_e}"
                if rec.company_id:
                    rec.name = f"{label} ({rec.company_id.name})"
                else:
                    rec.name = label
            else:
                rec.name = False

    @api.depends('period1_start_month', 'period1_end_month',
                 'period2_start_month', 'period2_end_month')
    def _compute_summary(self):
        for rec in self:
            m1_s = MONTH_NAMES.get(rec.period1_start_month, '')
            m1_e = MONTH_NAMES.get(rec.period1_end_month, '')
            m2_s = MONTH_NAMES.get(rec.period2_start_month, '')
            m2_e = MONTH_NAMES.get(rec.period2_end_month, '')
            if m1_s and m1_e and m2_s and m2_e:
                rec.summary = f"Period 1: {m1_s} to {m1_e} | Period 2: {m2_s} to {m2_e}"
            else:
                rec.summary = False

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("Effective From date cannot be later than Effective To date."))

    @api.constrains('period1_start_month', 'period1_end_month',
                    'period2_start_month', 'period2_end_month')
    def _check_months(self):
        for rec in self:
            if not (rec.period1_start_month and rec.period1_end_month and
                    rec.period2_start_month and rec.period2_end_month):
                raise ValidationError(_("All 4 month fields are required for the contribution periods."))
