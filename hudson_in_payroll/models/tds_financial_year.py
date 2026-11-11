# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class TdsFinancialYear(models.Model):
    """
    TDS Financial Year Master Model.
    Manages Indian Income Tax Financial Years (e.g. FY 2025-26) and Assessment Years (e.g. AY 2026-27).
    Serves as the root master linking income tax slabs, surcharge slabs, and default company tax years.
    """
    _name = 'tds.financial.year'
    _inherit = ['mail.thread']
    _description = 'TDS Financial Year'
    _order = 'code desc, id desc'

    _code_uniq = models.Constraint(
        'unique(code)',
        'A Financial Year with this code already exists. Financial Year Code must be unique!'
    )

    name = fields.Char(
        string="Tax Year Name",
        required=True,
        help="e.g. Tax Year: 2026-27"
    )
    code = fields.Char(
        string="Tax Year Code",
        required=True,
        help="e.g. 2025-2026"
    )
    assessment_year = fields.Char(
        string="Assessment Year",
        required=True,
        help="e.g. 2026-2027"
    )
    start_date = fields.Date(
        string="Start Date",
        required=True,
        help="Start date of the financial year (e.g. 01/04/2025)"
    )
    end_date = fields.Date(
        string="End Date",
        required=True,
        help="End date of the financial year (e.g. 31/03/2026)"
    )
    is_closed = fields.Boolean(
        string="Closed",
        default=False,
        help="Mark as true once the financial year is officially closed for tax declarations and payroll processing."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Set to false to archive old financial years."
    )
    tax_slab_ids = fields.One2many(
        'tds.tax.slab',
        'financial_year_id',
        string="All Income Tax Slabs"
    )
    new_regime_tax_slab_ids = fields.One2many(
        'tds.tax.slab',
        'financial_year_id',
        domain=[('regime_code', '=', 'new')],
        string="New Regime Tax Slabs"
    )
    old_regime_tax_slab_ids = fields.One2many(
        'tds.tax.slab',
        'financial_year_id',
        domain=[('regime_code', '=', 'old')],
        string="Old Regime Tax Slabs"
    )
    surcharge_ids = fields.One2many(
        'tds.surcharge',
        'financial_year_id',
        string="All Surcharge Slabs"
    )
    new_regime_surcharge_ids = fields.One2many(
        'tds.surcharge',
        'financial_year_id',
        domain=[('regime_code', '=', 'new')],
        string="New Regime Surcharge Slabs"
    )
    old_regime_surcharge_ids = fields.One2many(
        'tds.surcharge',
        'financial_year_id',
        domain=[('regime_code', '=', 'old')],
        string="Old Regime Surcharge Slabs"
    )
    is_proof_submission_open = fields.Boolean(
        string="Proof Submission Window Open",
        default=False,
        help="Enable to allow employees to upload investment proof documents for this Financial Year."
    )
    proof_submission_start_date = fields.Date(
        string="Proof Window Start Date",
        help="Date when HR opens December investment proof window."
    )
    proof_submission_end_date = fields.Date(
        string="Proof Window End Date",
        help="Date when December investment proof window closes."
    )
    declaration_cutoff_date = fields.Date(
        string="Declaration Cutoff Date",
        help="Company defined cutoff date for employee investment plan updates."
    )
    tds_recalculation_from_month = fields.Selection([
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
    ], string="Recalculation From Month", compute='_compute_tds_recalculation_from_month', store=True, readonly=False,
       help="Month from which post-proof-verification TDS recalculation starts (dynamically derived from Distribution Months).")

    tds_month_division = fields.Integer(
        string="TDS Month Division",
        default=12,
        required=True,
        help="Number of months to divide annual estimated TDS tax liability across regular monthly pay periods (Default: 12)."
    )

    tds_recalculation_distribution_months = fields.Integer(
        string="Distribution Months",
        default=3,
        required=True,
        help="Number of future payroll months over which recalculated remaining annual TDS liability is distributed (e.g., 3 for Jan, Feb, Mar)."
    )

    @api.depends('tds_recalculation_distribution_months')
    def _compute_tds_recalculation_from_month(self):
        for rec in self:
            dist_m = max(1, min(12, int(rec.tds_recalculation_distribution_months or 3)))
            start_fy_idx = 12 - dist_m + 1
            cal_m = (start_fy_idx + 2) % 12 + 1
            rec.tds_recalculation_from_month = str(cal_m)

    @api.model
    def _distribution_months_from_month(self, month):
        """Payroll months from the recalculation month to March, the end of the tax year
        (December -> 4: Dec, Jan, Feb, Mar). Reverse of _compute_tds_recalculation_from_month."""
        fy_index = (int(month) - 4) % 12 + 1  # April = 1 ... March = 12
        return 13 - fy_index

    @api.onchange('tds_recalculation_from_month')
    def _onchange_tds_recalculation_from_month(self):
        for rec in self:
            if rec.tds_recalculation_from_month:
                rec.tds_recalculation_distribution_months = self._distribution_months_from_month(rec.tds_recalculation_from_month)

    @api.model
    def _sync_recalculation_months(self, vals):
        """A month saved without its distribution months (e.g. from code) sets them too."""
        if vals.get('tds_recalculation_from_month') and 'tds_recalculation_distribution_months' not in vals:
            vals = dict(vals, tds_recalculation_distribution_months=self._distribution_months_from_month(
                vals['tds_recalculation_from_month']))
        return vals

    @api.model
    def default_get(self, fields_list):
        res = super(TdsFinancialYear, self).default_get(fields_list)
        # 1. Look for the latest financial year to clone slabs and surcharges from
        source_fy = self.search([('active', '=', True)], order='end_date desc, id desc', limit=1)
        if not source_fy:
            source_fy = self.with_context(active_test=False).search([], order='end_date desc, id desc', limit=1)

        if source_fy:
            try:
                start_yr = source_fy.start_date.year + 1
                end_yr = source_fy.end_date.year + 1
                if 'start_date' in fields_list and not res.get('start_date'):
                    res['start_date'] = fields.Date.from_string(f"{start_yr}-04-01")
                if 'end_date' in fields_list and not res.get('end_date'):
                    res['end_date'] = fields.Date.from_string(f"{end_yr}-03-31")
                if 'code' in fields_list and not res.get('code'):
                    res['code'] = f"{start_yr}-{end_yr}"
                if 'assessment_year' in fields_list and not res.get('assessment_year'):
                    res['assessment_year'] = f"{end_yr}-{end_yr + 1}"
                if 'name' in fields_list and not res.get('name'):
                    res['name'] = f"Tax Year: {start_yr}-{str(end_yr)[-2:]}"
            except Exception:
                pass

            target_date = res.get('start_date') or source_fy.start_date
            # Pre-populate tax slabs from source_fy
            if 'tax_slab_ids' in fields_list and not res.get('tax_slab_ids'):
                tax_slabs = []
                for slab in source_fy.tax_slab_ids:
                    tax_slabs.append((0, 0, {
                        'regime_id': slab.regime_id.id,
                        'regime_code': slab.regime_code,
                        'age_category': slab.age_category,
                        'sequence': slab.sequence,
                        'income_from': slab.income_from,
                        'income_to': slab.income_to,
                        'rate': slab.rate,
                        'date_from': target_date,
                        'active': True,
                    }))
                if tax_slabs:
                    res['tax_slab_ids'] = tax_slabs

            # Pre-populate surcharge slabs from source_fy
            if 'surcharge_ids' in fields_list and not res.get('surcharge_ids'):
                surcharges = []
                for sur in source_fy.surcharge_ids:
                    surcharges.append((0, 0, {
                        'regime_id': sur.regime_id.id,
                        'regime_code': sur.regime_code,
                        'sequence': sur.sequence,
                        'income_from': sur.income_from,
                        'income_to': sur.income_to,
                        'surcharge_rate': sur.surcharge_rate,
                        'date_from': target_date,
                        'active': True,
                    }))
                if surcharges:
                    res['surcharge_ids'] = surcharges
        else:
            # Fallback if no financial year exists at all in the database: propose 2026-2027 defaults
            if 'start_date' in fields_list and not res.get('start_date'):
                res['start_date'] = fields.Date.from_string("2026-04-01")
            if 'end_date' in fields_list and not res.get('end_date'):
                res['end_date'] = fields.Date.from_string("2027-03-31")
            if 'code' in fields_list and not res.get('code'):
                res['code'] = "2026-2027"
            if 'assessment_year' in fields_list and not res.get('assessment_year'):
                res['assessment_year'] = "2027-2028"
            if 'name' in fields_list and not res.get('name'):
                res['name'] = "Tax Year: 2026-27"

            regime_new = self.env.ref('hudson_in_payroll.hds_in_tds_regime_new', raise_if_not_found=False) or self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
            regime_old = self.env.ref('hudson_in_payroll.hds_in_tds_regime_old', raise_if_not_found=False) or self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)
            date_from = res.get('start_date') or fields.Date.from_string("2026-04-01")

            if 'tax_slab_ids' in fields_list and not res.get('tax_slab_ids'):
                default_slabs = []
                if regime_new:
                    new_slabs = [
                        (1, 0.0, 400000.0, 0.0),
                        (2, 400000.0, 800000.0, 5.0),
                        (3, 800000.0, 1200000.0, 10.0),
                        (4, 1200000.0, 1600000.0, 15.0),
                        (5, 1600000.0, 2000000.0, 20.0),
                        (6, 2000000.0, 2400000.0, 25.0),
                        (7, 2400000.0, 0.0, 30.0),
                    ]
                    for seq, inc_from, inc_to, rate in new_slabs:
                        default_slabs.append((0, 0, {
                            'regime_id': regime_new.id,
                            'regime_code': 'new',
                            'sequence': seq,
                            'income_from': inc_from,
                            'income_to': inc_to,
                            'rate': rate,
                            'date_from': date_from,
                            'active': True,
                        }))
                if regime_old:
                    old_slabs = [
                        (10, 0.0, 250000.0, 0.0),
                        (11, 250000.0, 500000.0, 5.0),
                        (12, 500000.0, 1000000.0, 20.0),
                        (13, 1000000.0, 0.0, 30.0),
                    ]
                    for seq, inc_from, inc_to, rate in old_slabs:
                        default_slabs.append((0, 0, {
                            'regime_id': regime_old.id,
                            'regime_code': 'old',
                            'sequence': seq,
                            'income_from': inc_from,
                            'income_to': inc_to,
                            'rate': rate,
                            'date_from': date_from,
                            'active': True,
                        }))
                if default_slabs:
                    res['tax_slab_ids'] = default_slabs

            if 'surcharge_ids' in fields_list and not res.get('surcharge_ids'):
                default_sur = []
                if regime_new:
                    sur_new = [
                        (1, 0.0, 5000000.0, 0.0),
                        (2, 5000000.0, 10000000.0, 10.0),
                        (3, 10000000.0, 20000000.0, 15.0),
                        (4, 20000000.0, 0.0, 25.0),
                    ]
                    for seq, inc_from, inc_to, srate in sur_new:
                        default_sur.append((0, 0, {
                            'regime_id': regime_new.id,
                            'regime_code': 'new',
                            'sequence': seq,
                            'income_from': inc_from,
                            'income_to': inc_to,
                            'surcharge_rate': srate,
                            'date_from': date_from,
                            'active': True,
                        }))
                if regime_old:
                    sur_old = [
                        (10, 0.0, 5000000.0, 0.0),
                        (11, 5000000.0, 10000000.0, 10.0),
                        (12, 10000000.0, 20000000.0, 15.0),
                        (13, 20000000.0, 50000000.0, 25.0),
                        (14, 50000000.0, 0.0, 37.0),
                    ]
                    for seq, inc_from, inc_to, srate in sur_old:
                        default_sur.append((0, 0, {
                            'regime_id': regime_old.id,
                            'regime_code': 'old',
                            'sequence': seq,
                            'income_from': inc_from,
                            'income_to': inc_to,
                            'surcharge_rate': srate,
                            'date_from': date_from,
                            'active': True,
                        }))
                if default_sur:
                    res['surcharge_ids'] = default_sur

        return res

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The Financial Year Code must be unique!')
    ]

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date >= rec.end_date:
                raise ValidationError(_("Financial Year Start Date (%s) must be earlier than End Date (%s).") % (
                    rec.start_date, rec.end_date
                ))

    def write(self, vals):
        for rec in self:
            if rec.is_closed and 'is_closed' not in vals:
                raise ValidationError(_("Financial Year '%s' is closed and locked. Reopen the Financial Year to make statutory modifications.") % rec.name)
        return super(TdsFinancialYear, self).write(self._sync_recalculation_months(vals))

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._sync_recalculation_months(vals) for vals in vals_list])

    def action_close_financial_year(self):
        for rec in self:
            rec.write({'is_closed': True})
            rec.message_post(body=_("Financial Year %s closed and locked against structural edits.") % rec.name)

    def action_unclose_financial_year(self):
        for rec in self:
            rec.write({'is_closed': False})
            rec.message_post(body=_("Financial Year %s reopened for administrative modifications.") % rec.name)

    def is_declaration_revision_allowed(self, eval_date=None):
        """Returns True if investment declaration updates are allowed for this financial year."""
        self.ensure_one()
        if self.is_closed:
            return False
        eval_date = eval_date or fields.Date.today()
        if self.declaration_cutoff_date:
            return eval_date <= self.declaration_cutoff_date
        return True

    def is_proof_submission_active(self, eval_date=None):
        """Returns True if the proof submission window is active for this financial year based on configured dates."""
        self.ensure_one()
        if self.is_closed:
            return False
        eval_date = eval_date or fields.Date.today()
        if self.proof_submission_start_date and self.proof_submission_end_date:
            return self.proof_submission_start_date <= eval_date <= self.proof_submission_end_date
        elif self.proof_submission_start_date:
            return eval_date >= self.proof_submission_start_date
        elif self.proof_submission_end_date:
            return eval_date <= self.proof_submission_end_date
        return eval_date.month in (12, 1)  # Default December - January proof submission window


