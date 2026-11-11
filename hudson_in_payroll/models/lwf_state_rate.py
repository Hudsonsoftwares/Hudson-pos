# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError

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


class LwfStateRate(models.Model):
    """
    Master Configuration Model for Indian Labour Welfare Fund (LWF) State Rates.
    Serves as the Single Source of Truth for state-wise LWF contribution amounts,
    deduction frequencies, statutory thresholds, and effective date ranges.
    """
    _name = 'lwf.state.rate'
    _description = 'Labour Welfare Fund State Rate'
    _order = 'state_id, date_from desc, id desc'

    def _auto_init(self):
        """
        Ensure authoritative Indian statutory LWF state rates are global (company_id = NULL)
        so they are automatically visible and usable across all companies nationwide.
        """
        res = super()._auto_init()
        cr = self.env.cr
        try:
            cr.execute("""
                UPDATE lwf_state_rate
                SET company_id = NULL
                WHERE id IN (
                    SELECT res_id FROM ir_model_data
                    WHERE model = 'lwf.state.rate'
                      AND module = 'hudson_in_payroll'
                );
            """)
        except Exception:
            pass
        return res

    name = fields.Char(
        string="Configuration Name",
        compute="_compute_name",
        store=True,
        help="Automated name summarizing state, frequency, and effective date."
    )
    state_id = fields.Many2one(
        'res.country.state',
        string="State",
        required=True,
        domain="[('country_id.code', '=', 'IN')]",
        help="Applicable Indian State for this LWF rate configuration."
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        default=lambda self: self.env.company.currency_id.id,
        help="Currency for monetary contribution amounts."
    )
    emp_contribution = fields.Monetary(
        string="Employee Contribution",
        currency_field='currency_id',
        required=True,
        default=0.0,
        help="Deduction amount contributed by the employee."
    )
    empl_contribution = fields.Monetary(
        string="Employer Contribution",
        currency_field='currency_id',
        required=True,
        default=0.0,
        help="Contribution amount paid by the employer."
    )
    deduction_frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('half_yearly', 'Half-Yearly'),
        ('annual', 'Annual'),
    ], string="Contribution Frequency", default='half_yearly', required=True,
        help="Deduction frequency mandated by state LWF rules.")

    deduction_month_1 = fields.Selection(
        MONTH_SELECTION,
        string="Contribution Month 1",
        default='6',
        help="Primary deduction month (e.g. June for half-yearly, December for annual)."
    )
    deduction_month_2 = fields.Selection(
        MONTH_SELECTION,
        string="Contribution Month 2",
        default='12',
        help="Second deduction month (used for half-yearly state rules e.g. December)."
    )
    date_from = fields.Date(
        string="Effective From",
        required=True,
        default=fields.Date.today,
        help="Start date from which this statutory rate configuration is effective."
    )
    date_to = fields.Date(
        string="Effective To",
        help="Optional end date until which this statutory rate configuration is effective."
    )
    min_employee_count = fields.Integer(
        string="Minimum Employee Count",
        default=0,
        help="Minimum establishment headcount threshold for LWF applicability (0 = applies to all establishments)."
    )
    notification_ref = fields.Char(
        string="Government Notification Reference",
        help="Official government notification, act amendment, or gazette reference for audit compliance."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Deactivate to archive this record."
    )
    remarks = fields.Text(
        string="Remarks",
        help="Additional statutory applicability notes or legal caveats."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=False,
        help="Optional company for multi-company isolation. Leave blank for global applicability."
    )

    @api.depends('state_id', 'deduction_frequency', 'date_from', 'company_id')
    def _compute_name(self):
        freq_labels = dict(self._fields['deduction_frequency'].selection)
        for rec in self:
            state_name = rec.state_id.name or _('Unset State')
            freq = freq_labels.get(rec.deduction_frequency, str(rec.deduction_frequency))
            date_str = fields.Date.to_string(rec.date_from) if rec.date_from else ''
            label = f"{state_name} - {freq} ({date_str})"
            if rec.company_id:
                rec.name = f"{label} ({rec.company_id.name})"
            else:
                rec.name = label

    @api.constrains('emp_contribution', 'empl_contribution')
    def _check_contributions(self):
        for rec in self:
            if rec.emp_contribution < 0.0 or rec.empl_contribution < 0.0:
                raise ValidationError(_("Contribution amounts cannot be negative."))

    @api.constrains('min_employee_count')
    def _check_min_employee_count(self):
        for rec in self:
            if rec.min_employee_count < 0:
                raise ValidationError(_("Minimum Employee Count cannot be negative."))

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise ValidationError(_("Effective To date (%s) cannot be earlier than Effective From date (%s).") % (rec.date_to, rec.date_from))

    @api.constrains('state_id', 'company_id', 'date_from', 'date_to', 'active')
    def _check_overlapping_dates(self):
        for rec in self:
            if not rec.active or not rec.state_id:
                continue
            if rec.company_id:
                domain = [
                    ('id', '!=', rec.id),
                    ('state_id', '=', rec.state_id.id),
                    ('active', '=', True),
                    ('company_id', '=', rec.company_id.id),
                ]
            else:
                domain = [
                    ('id', '!=', rec.id),
                    ('state_id', '=', rec.state_id.id),
                    ('active', '=', True),
                    ('company_id', '=', False),
                ]
            others = self.search(domain)
            for other in others:
                r_start = rec.date_from
                r_end = rec.date_to or fields.Date.from_string('2099-12-31')
                o_start = other.date_from
                o_end = other.date_to or fields.Date.from_string('2099-12-31')
                if (r_start <= o_end) and (r_end >= o_start):
                    raise ValidationError(_(
                        "Overlapping active LWF configuration found for state '%s' between period [%s to %s] and existing record '%s' [%s to %s]."
                    ) % (rec.state_id.name, r_start, rec.date_to or 'Indefinite', other.name, o_start, other.date_to or 'Indefinite'))

    def is_deduction_month(self, eval_date):
        """
        Evaluates whether eval_date's month is a scheduled deduction month for this state configuration.
        :param eval_date: datetime.date object
        :return: bool
        """
        self.ensure_one()
        if not eval_date:
            return False
        month_str = str(eval_date.month)
        if self.deduction_frequency == 'monthly':
            return True
        elif self.deduction_frequency == 'half_yearly':
            return month_str in (self.deduction_month_1, self.deduction_month_2)
        elif self.deduction_frequency == 'annual':
            return month_str == self.deduction_month_1
        return False
