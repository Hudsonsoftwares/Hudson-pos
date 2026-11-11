import logging
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class TdsEmployeeDeclarationLine(models.Model):
    """
    TDS Employee Tax Declaration Line Item Model.
    Captures individual investment proofs, Section 10 exemptions, and Chapter VI-A deduction line items.
    Enforces regime compatibility and statutory ceiling calculations.
    """
    _name = 'tds.employee.declaration.line'
    _description = 'Employee Tax Declaration Line Item'
    _order = 'declaration_id, category, id'

    declaration_id = fields.Many2one(
        'tds.employee.declaration',
        string="Declaration Header",
        required=True,
        ondelete='cascade',
        help="Parent declaration header."
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        related='declaration_id.employee_id',
        store=True,
        readonly=True
    )
    financial_year_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        related='declaration_id.financial_year_id',
        store=True,
        readonly=True
    )
    regime_code = fields.Selection(
        related='declaration_id.regime_code',
        string="Regime Code",
        store=True,
        readonly=True
    )
    declaration_state = fields.Selection(
        related='declaration_id.state',
        string="Declaration State",
        store=True,
        readonly=True
    )
    hds_in_is_agnipath = fields.Boolean(
        string="Employee under Agnipath Scheme",
        related='declaration_id.hds_in_is_agnipath',
        store=True,
        readonly=True
    )
    is_proof_window_open = fields.Boolean(
        string="Proof Window Open",
        related='declaration_id.is_proof_window_open',
        store=False,
        readonly=True
    )

    CATEGORY_NEW_SELECTION = [
        ('57iia', 'Family Pension — Section 93(1)(d) (Both Regimes)'),
    ]

    CATEGORY_NEW_AGNIPATH_SELECTION = [
        ('57iia', 'Family Pension — Section 93(1)(d) (Both Regimes)'),
        ('80cch', 'Section 80CCH Agniveer Corpus Fund Contribution (Both Regimes)'),
    ]

    CATEGORY_OLD_SELECTION = [
        ('80c', 'Section 80C (PPF, ELSS, LIC, Tuition Fee, EPF)'),
        ('80ccd1b', 'Section 80CCD(1B) Additional NPS Contribution'),
        ('80d_self', 'Section 80D Medical Insurance (Self & Family)'),
        ('80d_parents', 'Section 80D Medical Insurance (Parents)'),
        ('80d_preventive', 'Section 80D Preventive Health Checkup'),
        ('80tta', 'Section 80TTA Savings Interest (Non-Senior)'),
        ('80ttb', 'Section 80TTB Savings & FD Interest (Senior Citizen)'),
        ('80dd', 'Section 80DD Dependent Disability'),
        ('80u', 'Section 80U Employee Disability'),
        ('24b', 'Section 24(b) Home Loan Interest (Self-Occupied)'),
        ('80eea', 'Section 80EEA First-time Home Loan Additional Interest'),
        ('80e', 'Section 80E Education Loan Interest'),
        ('80g', 'Section 80G Charitable Donations'),
        ('80gg', 'Section 80GG Rent Paid without HRA'),
        ('hra', 'Section 10(13A) House Rent Exemption (Rent Paid)'),
        ('children_edu', 'Section 10(14) Children Education Allowance'),
        ('hostel', 'Section 10(14) Hostel Expenditure Allowance'),
        ('lta', 'Section 10(5) Leave Travel Assistance (LTA)'),
        ('nps_employee', 'Section 80CCD(1) Employee NPS Contribution'),
        ('57iia', 'Family Pension — Section 93(1)(d) (Both Regimes)'),
        ('leave_encashment', 'Section 10(10AA) Leave Encashment Exemption'),
        ('vrs', 'Section 10(10C) VRS Compensation Exemption'),
        ('other', 'Other Statutory Exemptions'),
    ]

    CATEGORY_OLD_AGNIPATH_SELECTION = [
        ('80c', 'Section 80C (PPF, ELSS, LIC, Tuition Fee, EPF)'),
        ('80ccd1b', 'Section 80CCD(1B) Additional NPS Contribution'),
        ('80d_self', 'Section 80D Medical Insurance (Self & Family)'),
        ('80d_parents', 'Section 80D Medical Insurance (Parents)'),
        ('80d_preventive', 'Section 80D Preventive Health Checkup'),
        ('80tta', 'Section 80TTA Savings Interest (Non-Senior)'),
        ('80ttb', 'Section 80TTB Savings & FD Interest (Senior Citizen)'),
        ('80dd', 'Section 80DD Dependent Disability'),
        ('80u', 'Section 80U Employee Disability'),
        ('24b', 'Section 24(b) Home Loan Interest (Self-Occupied)'),
        ('80eea', 'Section 80EEA First-time Home Loan Additional Interest'),
        ('80e', 'Section 80E Education Loan Interest'),
        ('80g', 'Section 80G Charitable Donations'),
        ('80gg', 'Section 80GG Rent Paid without HRA'),
        ('hra', 'Section 10(13A) House Rent Exemption (Rent Paid)'),
        ('children_edu', 'Section 10(14) Children Education Allowance'),
        ('hostel', 'Section 10(14) Hostel Expenditure Allowance'),
        ('lta', 'Section 10(5) Leave Travel Assistance (LTA)'),
        ('nps_employee', 'Section 80CCD(1) Employee NPS Contribution'),
        ('57iia', 'Family Pension — Section 93(1)(d) (Both Regimes)'),
        ('80cch', 'Section 80CCH Agniveer Corpus Fund Contribution (Both Regimes)'),
        ('leave_encashment', 'Section 10(10AA) Leave Encashment Exemption'),
        ('vrs', 'Section 10(10C) VRS Compensation Exemption'),
        ('other', 'Other Statutory Exemptions'),
    ]

    category = fields.Selection([
        ('80c', 'Section 80C (PPF, ELSS, LIC, Tuition Fee, EPF)'),
        ('80ccd1b', 'Section 80CCD(1B) Additional NPS Contribution'),
        ('80d_self', 'Section 80D Medical Insurance (Self & Family)'),
        ('80d_parents', 'Section 80D Medical Insurance (Parents)'),
        ('80d_preventive', 'Section 80D Preventive Health Checkup'),
        ('80tta', 'Section 80TTA Savings Interest (Non-Senior)'),
        ('80ttb', 'Section 80TTB Savings & FD Interest (Senior Citizen)'),
        ('80dd', 'Section 80DD Dependent Disability'),
        ('80u', 'Section 80U Employee Disability'),
        ('24b', 'Section 24(b) Home Loan Interest (Self-Occupied)'),
        ('80eea', 'Section 80EEA First-time Home Loan Additional Interest'),
        ('80e', 'Section 80E Education Loan Interest'),
        ('80g', 'Section 80G Charitable Donations'),
        ('80gg', 'Section 80GG Rent Paid without HRA'),
        ('hra', 'Section 10(13A) House Rent Exemption (Rent Paid)'),
        ('children_edu', 'Section 10(14) Children Education Allowance'),
        ('hostel', 'Section 10(14) Hostel Expenditure Allowance'),
        ('lta', 'Section 10(5) Leave Travel Assistance (LTA)'),
        ('nps_employee', 'Section 80CCD(1) Employee NPS Contribution'),
        ('80ccd2', 'Employer NPS Contribution — Section 124 (Both Regimes)'),
        ('57iia', 'Family Pension — Section 93(1)(d) (Both Regimes)'),
        ('80cch', 'Section 80CCH Agniveer Corpus Fund Contribution (Both Regimes)'),
        ('leave_encashment', 'Section 10(10AA) Leave Encashment Exemption'),
        ('vrs', 'Section 10(10C) VRS Compensation Exemption'),
        ('other', 'Other Statutory Exemptions'),
    ], string="Declaration Category", required=False)

    category_new = fields.Selection(
        selection=CATEGORY_NEW_SELECTION,
        string="Declaration Category",
        compute='_compute_ui_categories',
        inverse='_inverse_category_new',
        store=True,
        help="Statutory investment and deduction categories permitted under New Tax Regime."
    )

    category_new_agnipath = fields.Selection(
        selection=CATEGORY_NEW_AGNIPATH_SELECTION,
        string="Declaration Category",
        compute='_compute_ui_categories',
        inverse='_inverse_category_new_agnipath',
        store=True,
        help="Statutory investment and deduction categories permitted under New Tax Regime for Agnipath scheme."
    )

    category_old = fields.Selection(
        selection=CATEGORY_OLD_SELECTION,
        string="Declaration Category",
        compute='_compute_ui_categories',
        inverse='_inverse_category_old',
        store=True,
        help="Statutory investment and deduction categories permitted under Old Tax Regime."
    )

    category_old_agnipath = fields.Selection(
        selection=CATEGORY_OLD_AGNIPATH_SELECTION,
        string="Declaration Category",
        compute='_compute_ui_categories',
        inverse='_inverse_category_old_agnipath',
        store=True,
        help="Statutory investment and deduction categories permitted under Old Tax Regime for Agnipath scheme."
    )

    @api.depends('category')
    def _compute_ui_categories(self):
        new_cats = dict(self.CATEGORY_NEW_SELECTION)
        new_ag_cats = dict(self.CATEGORY_NEW_AGNIPATH_SELECTION)
        old_cats = dict(self.CATEGORY_OLD_SELECTION)
        old_ag_cats = dict(self.CATEGORY_OLD_AGNIPATH_SELECTION)
        for line in self:
            c = line.category
            line.category_new = c if c in new_cats else False
            line.category_new_agnipath = c if c in new_ag_cats else False
            line.category_old = c if c in old_cats else False
            line.category_old_agnipath = c if c in old_ag_cats else False

    def _inverse_category_new(self):
        for line in self:
            if line.category_new and line.category != line.category_new:
                line.category = line.category_new

    def _inverse_category_new_agnipath(self):
        for line in self:
            if line.category_new_agnipath and line.category != line.category_new_agnipath:
                line.category = line.category_new_agnipath

    def _inverse_category_old(self):
        for line in self:
            if line.category_old and line.category != line.category_old:
                line.category = line.category_old

    def _inverse_category_old_agnipath(self):
        for line in self:
            if line.category_old_agnipath and line.category != line.category_old_agnipath:
                line.category = line.category_old_agnipath

    @api.onchange('category_new', 'category_new_agnipath', 'category_old', 'category_old_agnipath')
    def _onchange_ui_categories(self):
        selected = self.category_new or self.category_new_agnipath or self.category_old or self.category_old_agnipath
        if selected:
            self.category = selected
            if not self.description:
                desc_map = {
                    '57iia': 'Family Pension Received (annual) — Section 93(1)(d)',
                    '80cch': 'Agniveer Corpus Fund Contribution (80CCH)',
                    '80c': 'Section 80C Specified Investments',
                    '80ccd1b': 'Additional NPS Contribution u/s 80CCD(1B)',
                    '80d_self': 'Medical Insurance Premium (Self & Family)',
                    '80d_parents': 'Medical Insurance Premium (Parents)',
                    '80d_preventive': 'Preventive Health Checkup',
                    '24b': 'Interest on Housing Loan (Self-Occupied)',
                    'hra': 'House Rent Allowance (Section 10(13A))',
                }
                self.description = desc_map.get(selected, False)

    @api.constrains('category', 'category_new', 'category_new_agnipath', 'category_old', 'category_old_agnipath')
    def _check_category_mandatory(self):
        for line in self:
            if not any([line.category, line.category_new, line.category_new_agnipath, line.category_old, line.category_old_agnipath]):
                raise ValidationError(_("Please select an investment category for declaration line '%s'.") % (line.description or 'Line Item'))



    section_code = fields.Char(
        string="Statutory Section Code",
        compute='_compute_section_code',
        store=False,
        help="Automated section code designation."
    )
    description = fields.Char(
        string="Investment Particulars / Description",
        required=True,
        help="Detailed description of investment or claim (e.g. LIC Policy #98765, Rent Paid to Landlord)."
    )
    declared_amount = fields.Monetary(
        string="Declared Amount (₹)",
        currency_field='currency_id',
        required=True,
        default=0.0,
        help="Amount declared by employee."
    )
    is_senior_citizen = fields.Boolean(
        string="Insured Person is Senior Citizen (Age ≥ 60)",
        default=False,
        help="Mark True if the insured person (Self/Spouse or Parents) is a Senior Citizen (Age 60+), unlocking higher Section 80D statutory limits."
    )
    is_severe_disability = fields.Boolean(
        string="Severe Disability (Disability ≥ 80%)",
        default=False,
        help="Mark True if dependent disability is 80% or higher, unlocking higher Section 80DD statutory ceiling of ₹1,25,000."
    )
    decl_80g_category = fields.Selection([
        ('100_no_limit', '100% Deduction (Without Qualifying Limit)'),
        ('50_no_limit', '50% Deduction (Without Qualifying Limit)'),
        ('100_with_limit', '100% Deduction (Subject to Qualifying Limit)'),
        ('50_with_limit', '50% Deduction (Subject to Qualifying Limit)'),
    ], string="80G Deduction Category", help="Statutory category under Section 80G governing deduction percentage and qualifying limits.")

    # Section 10(13A) HRA Eligibility Validation Fields
    own_residential_property_at_workplace = fields.Boolean(
        string="Own Residential Property at Place of Work/Residence",
        default=False,
        help="Section 10(13A) - Mark True if employee owns residential accommodation at the place of work/residence."
    )
    rent_period_from = fields.Date(
        string="Rent Period From",
        help="Section 10(13A) - Start date of the claimed rent period."
    )
    rent_period_to = fields.Date(
        string="Rent Period To",
        help="Section 10(13A) - End date of the claimed rent period."
    )

    verified_amount = fields.Monetary(
        string="Verified Amount (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Amount verified by HR after proof document inspection."
    )

    approved_amount = fields.Monetary(
        string="Approved Statutory Deduction (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Final statutory deduction allowed after ceiling cap and regime validation."
    )
    tax_firm_approved_amount = fields.Monetary(
        string="Tax Firm Approved Amount (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Final deduction amount approved by external Tax Firm, entered manually by HR after proof verification."
    )
    rejected_amount = fields.Monetary(
        string="Rejected Amount (₹)",
        currency_field='currency_id',
        compute='_compute_rejected_amount',
        store=True,
        readonly=False,
        help="Amount rejected by HR during proof document verification."
    )

    @api.depends('declared_amount', 'approved_amount', 'tax_firm_approved_amount', 'declaration_id.state')
    def _compute_rejected_amount(self):
        for line in self:
            if line.declaration_id and line.declaration_id.state in ('proof_under_review', 'proof_verified', 'approved'):
                eff_approved = line.tax_firm_approved_amount or line.approved_amount or 0.0
                line.rejected_amount = max(0.0, (line.declared_amount or 0.0) - eff_approved)
            else:
                line.rejected_amount = 0.0

    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='declaration_id.currency_id',
        readonly=True
    )
    is_regime_permitted = fields.Boolean(
        string="Regime Permitted",
        default=True,
        help="True if deduction category is permitted under the employee's selected tax regime."
    )
    validation_status = fields.Selection([
        ('valid', 'Statutory Valid'),
        ('exceeds_limit', 'Exceeds Statutory Limit (Capped)'),
        ('ineligible_regime', 'Not Permitted Under New Regime'),
        ('pending_proof', 'Pending Document Proof'),
    ], string="Validation Status", default='valid', required=True)

    validation_remarks = fields.Text(
        string="Validation Remarks",
        help="Audit trail explaining statutory capping or regime rejection reasons."
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_declaration_line_ir_attachment_rel',
        'line_id',
        'attachment_id',
        string="Supporting Document Proofs",
        help="Proof receipts attached specifically for this investment line item."
    )

    @api.constrains('attachment_ids')
    def _check_single_attachment_per_line(self):
        for rec in self:
            if len(rec.attachment_ids) > 1:
                raise ValidationError(_(
                    "Maximum 1 file can be uploaded for investment line '%s'. Currently %d files are attached. "
                    "Please upload only 1 supporting document."
                ) % (rec.description or 'Investment Line', len(rec.attachment_ids)))

    @api.depends('category', 'category_new', 'category_new_agnipath', 'category_old', 'category_old_agnipath')
    def _compute_section_code(self):
        code_map = {
            '80c': 'Sec 80C',
            '80ccd1b': 'Sec 80CCD(1B)',
            '80d_self': 'Sec 80D (Self)',
            '80d_parents': 'Sec 80D (Parents)',
            '80d_preventive': 'Sec 80D (Preventive)',
            '80tta': 'Sec 80TTA',
            '80ttb': 'Sec 80TTB',
            '80dd': 'Sec 80DD',
            '80e': 'Sec 80E',
            '80g': 'Sec 80G',
            '80u': 'Sec 80U',
            '24b': 'Sec 24(b)',
            '80eea': 'Sec 80EEA',
            'hra': 'Sec 10(13A)',
            'children_edu': 'Sec 10(14)',
            'hostel': 'Sec 10(14)',
            'lta': 'Sec 10(5)',
            'nps_employee': 'Sec 80CCD(1)',
            '80ccd2': 'Sec 80CCD(2)',
            '57iia': 'Sec 93(1)(d)',
            '80cch': 'Sec 80CCH',
            'leave_encashment': 'Sec 10(10AA)',
            'vrs': 'Sec 10(10C)',
            'other': 'Other',
        }
        for line in self:
            cat = line.category or line.category_new or line.category_new_agnipath or line.category_old or line.category_old_agnipath
            line.section_code = code_map.get(cat, 'General')

    eligible_amount = fields.Monetary(
        string="Eligible Deduction (₹)",
        currency_field='currency_id',
        compute='_compute_deduction_eligibility',
        store=False,
        help="System-calculated allowable statutory deduction computed dynamically on-the-fly."
    )
    excess_amount = fields.Monetary(
        string="Excess / Non-Eligible Amount (₹)",
        currency_field='currency_id',
        compute='_compute_deduction_eligibility',
        store=False,
        help="Informational non-eligible investment portion exceeding statutory deduction limits."
    )

    @api.constrains('category', 'declared_amount', 'approved_amount', 'tax_firm_approved_amount', 'verified_amount', 'decl_80g_category')
    def _check_80g_category(self):
        for line in self:
            if line.category == '80g':
                decl_state = line.declaration_state or (line.declaration_id.state if line.declaration_id else 'draft')
                is_post_proof = decl_state in ('proof_under_review', 'proof_verified', 'approved')
                if is_post_proof:
                    eff_amount = float(line.tax_firm_approved_amount or line.approved_amount or line.verified_amount or line.declared_amount or 0.0)
                else:
                    eff_amount = float(line.declared_amount or 0.0)

                if eff_amount > 0.0 and not line.decl_80g_category:
                    raise ValidationError(_(
                        "Section 80G Deduction Category is mandatory for declaration line '%s' when a donation amount (₹%s) is declared or approved. "
                        "Please select a valid 80G category (100%% No Limit, 50%% No Limit, 100%% With Limit, or 50%% With Limit)."
                    ) % (line.description or 'Section 80G Donation', f"{eff_amount:,.2f}"))

    @api.depends('declared_amount', 'approved_amount', 'tax_firm_approved_amount', 'is_regime_permitted', 'category', 'category_new', 'category_new_agnipath', 'category_old', 'category_old_agnipath', 'declaration_id.state', 'regime_code', 'declaration_id.employee_id', 'declaration_id.financial_year_id')
    def _compute_deduction_eligibility(self):
        from ..services.tds.eligibility_rule_engine_service import EligibilityRuleEngineService
        engine = EligibilityRuleEngineService(self.env)
        for line in self:
            eval_d = line.declaration_id.financial_year_id.start_date if (line.declaration_id and line.declaration_id.financial_year_id and line.declaration_id.financial_year_id.start_date) else None
            res = engine.evaluate_eligibility(line, eval_date=eval_d)
            line.eligible_amount = res.eligible_deduction
            line.excess_amount = res.excess_amount

    @property
    def usable_amount(self):
        """
        Statutory usable amount for TDS calculation engines and reconciliation:
        - Planning Phase (state not in ('proof_verified', 'approved')): eligible_amount
        - Adjustment Phase (state in ('proof_verified', 'approved')):
          Reflects the post-proof approved/verified amount capped by statutory eligibility.
          If HR / Tax Firm rejected (Approved = 0), usable_amount is strictly 0.0.
        """
        self._compute_deduction_eligibility()

        res_amt = 0.0
        if self.declaration_id and self.declaration_id.state in ('proof_verified', 'approved'):
            tf_amt = float(self.tax_firm_approved_amount or 0.0)
            appr_amt = float(self.approved_amount or 0.0)
            ver_amt = float(self.verified_amount or 0.0)
            elig_amt = float(self.eligible_amount or 0.0)

            if tf_amt > 0.0:
                target_amt = tf_amt
            elif appr_amt > 0.0:
                target_amt = appr_amt
            elif ver_amt > 0.0:
                target_amt = ver_amt
            else:
                target_amt = 0.0

            res_amt = min(target_amt, elig_amt) if elig_amt > 0.0 else target_amt
        else:
            res_amt = self.eligible_amount if self.eligible_amount is not None else (self.declared_amount or 0.0)

        return res_amt

    UI_CAT_FIELDS = ('category_new', 'category_new_agnipath', 'category_old', 'category_old_agnipath')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            for f in self.UI_CAT_FIELDS:
                if vals.get(f) and not vals.get('category'):
                    vals['category'] = vals[f]
                    break
            if vals.get('category'):
                c = vals['category']
                if c in dict(self.CATEGORY_NEW_SELECTION) and not vals.get('category_new'):
                    vals['category_new'] = c
                if c in dict(self.CATEGORY_NEW_AGNIPATH_SELECTION) and not vals.get('category_new_agnipath'):
                    vals['category_new_agnipath'] = c
                if c in dict(self.CATEGORY_OLD_SELECTION) and not vals.get('category_old'):
                    vals['category_old'] = c
                if c in dict(self.CATEGORY_OLD_AGNIPATH_SELECTION) and not vals.get('category_old_agnipath'):
                    vals['category_old_agnipath'] = c

            if 'tax_firm_approved_amount' in vals and vals.get('tax_firm_approved_amount') is not False:
                tf_val = float(vals.get('tax_firm_approved_amount') or 0.0)
                if tf_val > 0.0 or 'approved_amount' not in vals:
                    vals['approved_amount'] = tf_val
            elif 'approved_amount' in vals and vals.get('approved_amount') is not False:
                appr_val = float(vals.get('approved_amount') or 0.0)
                if appr_val > 0.0 or 'tax_firm_approved_amount' not in vals:
                    vals['tax_firm_approved_amount'] = appr_val
        lines = super(TdsEmployeeDeclarationLine, self).create(vals_list)
        for line in lines:
            if line.declaration_id and line.attachment_ids:
                new_att = line.attachment_ids - line.declaration_id.attachment_ids
                if new_att:
                    line.declaration_id.attachment_ids = [(4, att.id) for att in new_att]
        return lines

    def write(self, vals):
        for f in self.UI_CAT_FIELDS:
            if vals.get(f) and not vals.get('category'):
                vals['category'] = vals[f]
                break
        if vals.get('category'):
            c = vals['category']
            if c in dict(self.CATEGORY_NEW_SELECTION) and not vals.get('category_new'):
                vals['category_new'] = c
            if c in dict(self.CATEGORY_NEW_AGNIPATH_SELECTION) and not vals.get('category_new_agnipath'):
                vals['category_new_agnipath'] = c
            if c in dict(self.CATEGORY_OLD_SELECTION) and not vals.get('category_old'):
                vals['category_old'] = c
            if c in dict(self.CATEGORY_OLD_AGNIPATH_SELECTION) and not vals.get('category_old_agnipath'):
                vals['category_old_agnipath'] = c

        sync_tf = 'tax_firm_approved_amount' in vals
        sync_appr = 'approved_amount' in vals

        if sync_tf and not sync_appr:
            vals['approved_amount'] = float(vals.get('tax_firm_approved_amount') or 0.0)
        elif sync_appr and not sync_tf:
            vals['tax_firm_approved_amount'] = float(vals.get('approved_amount') or 0.0)

        before_dict = {l.id: float(l.approved_amount or 0.0) for l in self}
        res = super(TdsEmployeeDeclarationLine, self).write(vals)

        for line in self:
            if sync_tf and line.approved_amount != line.tax_firm_approved_amount:
                super(TdsEmployeeDeclarationLine, line).write({'approved_amount': line.tax_firm_approved_amount})
            elif sync_appr and line.tax_firm_approved_amount != line.approved_amount:
                super(TdsEmployeeDeclarationLine, line).write({'tax_firm_approved_amount': line.approved_amount})
            if 'attachment_ids' in vals and line.declaration_id and line.attachment_ids:
                new_att = line.attachment_ids - line.declaration_id.attachment_ids
                if new_att:
                    line.declaration_id.attachment_ids = [(4, att.id) for att in new_att]

        return res

    def unlink(self):
        line_field_map = []
        for line in self:
            if line.declaration_id:
                target_f = line.declaration_id._resolve_declaration_field_for_line(line.category, line.description)
                if target_f:
                    line_field_map.append((line.declaration_id, target_f))
        res = super(TdsEmployeeDeclarationLine, self).unlink()
        for decl, target_f in line_field_map:
            if decl.exists() and hasattr(decl, target_f) and getattr(decl, target_f, 0.0):
                decl.with_context(no_line_sync=True).sudo().write({target_f: 0.0})
        return res

