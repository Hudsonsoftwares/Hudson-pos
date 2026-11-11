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


class PtStateSlab(models.Model):
    """
    Master Configuration Model for Indian Professional Tax (PT) State Slabs.
    Serves as the Single Source of Truth for state-wise Professional Tax salary ranges,
    fixed deduction amounts, deduction periodicity, special monthly overrides,
    effective-dated statutory changes, and multi-company support.
    """
    _name = 'pt.state.slab'
    _description = 'Professional Tax State Slab'
    _order = 'state_id, periodicity, salary_from, date_from desc, id desc'

    def _auto_init(self):
        """
        Clean up any stale database records from previous module upgrade attempts
        where gender defaulted to 'all' for Maharashtra records.
        """
        res = super()._auto_init()
        cr = self.env.cr
        try:
            cr.execute("""
                UPDATE pt_state_slab
                SET gender = 'male'
                WHERE gender IS NULL
                  AND state_id IN (SELECT id FROM res_country_state WHERE code = 'MH')
                  AND salary_from < 25000;
            """)
            cr.execute("""
                UPDATE pt_state_slab
                SET company_id = NULL
                WHERE id IN (
                    SELECT res_id FROM ir_model_data
                    WHERE model = 'pt.state.slab'
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
        help="Automated name summarizing state, periodicity, salary range, PT amount, and effective date."
    )
    state_id = fields.Many2one(
        'res.country.state',
        string="State",
        required=True,
        domain="[('country_id.code', '=', 'IN')]",
        help="Applicable Indian State for this Professional Tax slab configuration."
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        default=lambda self: self.env.company.currency_id.id,
        help="Currency for salary limits and Professional Tax amounts."
    )
    salary_from = fields.Monetary(
        string="Salary From",
        currency_field='currency_id',
        required=True,
        default=0.0,
        help="Lower limit of gross/taxable monthly salary slab (inclusive)."
    )
    salary_to = fields.Monetary(
        string="Salary To",
        currency_field='currency_id',
        required=False,
        help="Upper limit of gross/taxable monthly salary slab (inclusive). Leave blank for open-ended upper slab."
    )
    pt_amount = fields.Monetary(
        string="Professional Tax Amount",
        currency_field='currency_id',
        required=True,
        default=0.0,
        help="Fixed Professional Tax deduction amount for this salary slab."
    )
    periodicity = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('half_yearly', 'Half-Yearly'),
        ('annual', 'Annual'),
    ], string="Periodicity", default='monthly', required=True,
        help="Deduction periodicity mandated by state Professional Tax rules.")
    gender = fields.Selection([
        ('all', 'All / Unspecified'),
        ('male', 'Male Only'),
        ('female', 'Female Only'),
    ], string="Gender Criteria", default='all', required=True,
        help="Gender applicability criteria for this Professional Tax slab (e.g. Maharashtra gender-differentiated slabs).")

    override_month = fields.Selection(
        MONTH_SELECTION,
        string="Override Month",
        required=False,
        help="Calendar month in which the normal Professional Tax amount is overridden (e.g. February)."
    )
    override_amount = fields.Monetary(
        string="Override Amount",
        currency_field='currency_id',
        required=False,
        help="Professional Tax amount applicable during the override month."
    )

    date_from = fields.Date(
        string="Effective From",
        required=False,
        help="Start date from which this Professional Tax slab configuration is effective."
    )
    date_to = fields.Date(
        string="Effective To",
        help="Optional end date until which this Professional Tax slab configuration is effective."
    )
    notification_ref = fields.Char(
        string="Government Notification Reference",
        help="Official government notification, act amendment, or gazette reference for audit compliance."
    )
    special_rules = fields.Text(
        string="Special Rules",
        help="Special rules, gender variations, or month surcharges (e.g. Feb Rs 300, Female slab, etc.)."
    )
    remarks = fields.Text(
        string="Remarks",
        help="Additional statutory applicability notes, source references, or caveats."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Deactivate to archive this record without deletion."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=False,
        help="Optional company for multi-company isolation. Leave blank for global state applicability."
    )

    @api.depends('state_id', 'gender', 'salary_from', 'salary_to', 'pt_amount', 'periodicity', 'date_from')
    def _compute_name(self):
        periodicity_labels = dict(self._fields['periodicity'].selection)
        gender_labels = dict(self._fields['gender'].selection)
        for rec in self:
            state_name = rec.state_id.name or _('Unset State')
            sal_to_str = f"₹{rec.salary_to:,.0f}" if rec.salary_to else _("Above")
            period = periodicity_labels.get(rec.periodicity, str(rec.periodicity))
            gender_str = f" ({gender_labels.get(rec.gender)})" if rec.gender and rec.gender != 'all' else ''
            date_str = f" [{fields.Date.to_string(rec.date_from)}]" if rec.date_from else ''
            rec.name = f"{state_name}{gender_str} [{period}]: ₹{rec.salary_from:,.0f} - {sal_to_str} → PT ₹{rec.pt_amount:,.0f}{date_str}"

    @api.constrains('salary_from', 'salary_to')
    def _check_salary_range(self):
        for rec in self:
            if rec.salary_from < 0.0:
                raise ValidationError(_("Salary From cannot be negative."))
            if rec.salary_to and rec.salary_to < 0.0:
                raise ValidationError(_("Salary To cannot be negative."))
            if rec.salary_to and rec.salary_to < rec.salary_from:
                raise ValidationError(_("Salary To (₹%s) cannot be less than Salary From (₹%s).") % (rec.salary_to, rec.salary_from))

    @api.constrains('pt_amount')
    def _check_pt_amount(self):
        for rec in self:
            if rec.pt_amount < 0.0:
                raise ValidationError(_("Professional Tax Amount cannot be negative."))

    @api.constrains('override_amount')
    def _check_override_amount(self):
        for rec in self:
            if rec.override_amount and rec.override_amount < 0.0:
                raise ValidationError(_("Override Amount cannot be negative."))

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise ValidationError(_("Effective To date (%s) cannot be earlier than Effective From date (%s).") % (rec.date_to, rec.date_from))

    @api.constrains('state_id', 'company_id', 'periodicity', 'gender', 'salary_from', 'salary_to', 'date_from', 'date_to', 'active')
    def _check_overlapping_slabs(self):
        for rec in self:
            if not rec.active or not rec.state_id:
                continue
            domain = [
                ('id', 'not in', self.ids),
                ('state_id', '=', rec.state_id.id),
                ('periodicity', '=', rec.periodicity),
                ('active', '=', True),
            ]
            if rec.company_id:
                domain.append('|')
                domain.append(('company_id', '=', False))
                domain.append(('company_id', '=', rec.company_id.id))
            else:
                domain.append(('company_id', '=', False))

            others = self.search(domain)

            rec_date_start = rec.date_from or fields.Date.from_string('1900-01-01')
            rec_date_end = rec.date_to or fields.Date.from_string('2099-12-31')
            rec_sal_end = rec.salary_to if rec.salary_to else float('inf')

            for other in others:
                other_date_start = other.date_from or fields.Date.from_string('1900-01-01')
                other_date_end = other.date_to or fields.Date.from_string('2099-12-31')
                other_sal_end = other.salary_to if other.salary_to else float('inf')

                # Check gender overlap
                genders_overlap = (rec.gender == 'all') or (other.gender == 'all') or (rec.gender == other.gender)

                # Check date range overlap
                dates_overlap = (rec_date_start <= other_date_end) and (rec_date_end >= other_date_start)
                # Check salary range overlap
                salaries_overlap = (rec.salary_from <= other_sal_end) and (rec_sal_end >= other.salary_from)

                if genders_overlap and dates_overlap and salaries_overlap:
                    raise ValidationError(_(
                        "Overlapping active Professional Tax slab found for state '%s' [%s, %s] within salary range [₹%.2f to %s] matching existing record '%s'."
                    ) % (
                        rec.state_id.name,
                        rec.periodicity,
                        rec.gender,
                        rec.salary_from,
                        f"₹{rec.salary_to:.2f}" if rec.salary_to else 'Above',
                        other.name
                    ))
