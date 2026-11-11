# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class HdsLeaveEncashmentPolicy(models.Model):
    """
    Enterprise Leave Encashment Policy Configuration for Hudson Indian Payroll.
    Defines rules, eligibility criteria, buffer limits, and customizable formulas
    governing In-Service Leave Encashment.
    """
    _name = 'hds.leave.encashment.policy'
    _description = 'Leave Encashment Policy'
    _order = 'name asc'

    name = fields.Char(
        string="Policy Name",
        required=True,
        help="Descriptive name for this leave encashment policy (e.g. Standard Earned Leave Policy)."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=False,
        default=lambda self: self.env.company,
        help="Company to which this encashment policy applies. Leave blank for default policy across all companies."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="If unchecked, this policy will be hidden and cannot be used for new requests."
    )

    # -------------------------------------------------------------------------
    # 1. ELIGIBILITY GUARDS
    # -------------------------------------------------------------------------
    employee_type_ids = fields.Many2many(
        'hr.employee.type',
        'hds_policy_employee_type_rel',
        'policy_id',
        'type_id',
        string="Employee Type",
        help="Select eligible employee types configured in the Employee module (under Payroll tab). Leave blank to allow all employee types."
    )

    min_service_period_days = fields.Integer(
        string="Minimum Service Period (Days)",
        default=180,
        help="Minimum tenure (in days) an employee must complete from joining date before being eligible to encash leaves."
    )

    # -------------------------------------------------------------------------
    # 2. SELECTABLE TIME OFF TYPES
    # -------------------------------------------------------------------------
    leave_type_ids = fields.Many2many(
        'hr.work.entry.type',
        'hds_policy_work_entry_type_rel',
        'policy_id',
        'work_entry_type_id',
        string="Eligible Leave Types",
        domain="[('include_in_leave_encashment', '=', True)]",
        help="Select leave types eligible for encashment under this policy. Only types with 'Include in Leave Encashment' enabled can be chosen."
    )

    # -------------------------------------------------------------------------
    # 3. BUFFER RETENTION & MAXIMUM THRESHOLDS
    # -------------------------------------------------------------------------
    min_balance_to_maintain = fields.Float(
        string="Minimum Balance to Retain (Days)",
        default=5.0,
        help="Minimum days of leave that must remain in the employee's balance after encashment (retention safety buffer)."
    )
    max_encashable_days_per_year = fields.Float(
        string="Max Encashable Days / Fiscal Year",
        default=15.0,
        help="Maximum total days an employee is permitted to encash in a single financial year."
    )
    max_encashable_days_per_request = fields.Float(
        string="Max Encashable Days / Request",
        default=10.0,
        help="Maximum days that can be encashed in a single transaction request."
    )

    # -------------------------------------------------------------------------
    # 4. CALCULATION FORMULA ENGINE
    # -------------------------------------------------------------------------
    calculation_basis = fields.Selection([
        ('statutory_26', 'Statutory Standard: (Basic + DA) / 26'),
        ('calendar_30', 'Calendar Days: (Basic + DA) / 30'),
        ('gross_30', 'Gross Salary: Gross / 30'),
        ('custom_formula', 'Custom Python Formula Expression'),
    ], string="Calculation Basis", default='statutory_26', required=True,
       help="Formula method used to derive the daily wage rate for leave encashment.")

    custom_formula_code = fields.Text(
        string="Custom Formula Expression",
        default="result = ((basic + da) / 26.0) * encash_days",
        help="Python expression evaluated when 'Custom Formula' is selected.\n"
             "Available variables:\n"
             "• basic: Monthly Basic Salary\n"
             "• da: Monthly Dearness Allowance\n"
             "• gross: Total Monthly Gross Salary\n"
             "• encash_days: Number of days being encashed\n"
             "• contract: Active hr.version contract recordset\n"
             "• employee: hr.employee recordset\n"
             "Must set 'result' variable to the payable monetary float."
    )

    # -------------------------------------------------------------------------
    # 5. STATUTORY TAXATION & RETIRAL FLAGS
    # -------------------------------------------------------------------------
    taxable_for_tds = fields.Boolean(
        string="Subject to TDS (Section 17(1))",
        default=True,
        readonly=True,
        help="Under Indian Tax Law (Section 17(1)), in-service leave encashment is 100% taxable as salary income. Section 10(10AA) exemption does NOT apply during active service."
    )
    include_in_pf_wage = fields.Boolean(
        string="Include in PF Wage",
        default=False,
        help="Leave encashment is excluded from PF wages per Indian Supreme Court rulings."
    )
    include_in_esic_wage = fields.Boolean(
        string="Include in ESIC Wage",
        default=False,
        help="Leave encashment is excluded from ESIC wages under Section 2(22) of the ESI Act."
    )

    @api.constrains('min_service_period_days', 'min_balance_to_maintain', 'max_encashable_days_per_year', 'max_encashable_days_per_request')
    def _check_positive_limits(self):
        for rec in self:
            if rec.min_service_period_days < 0:
                raise ValidationError(_("Minimum service period cannot be negative."))
            if rec.min_balance_to_maintain < 0.0:
                raise ValidationError(_("Minimum balance to retain cannot be negative."))
            if rec.max_encashable_days_per_year <= 0.0:
                raise ValidationError(_("Max encashable days per year must be greater than zero."))
            if rec.max_encashable_days_per_request <= 0.0:
                raise ValidationError(_("Max encashable days per request must be greater than zero."))
            if rec.max_encashable_days_per_request > rec.max_encashable_days_per_year:
                raise ValidationError(_("Max encashable days per request cannot exceed the annual maximum limit."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.context.get('install_mode'):
                comp_id = vals.get('company_id')
                if comp_id:
                    comp = self.env['res.company'].browse(comp_id)
                    if comp and hasattr(comp, 'hds_in_enable_leave_encashment') and not comp.hds_in_enable_leave_encashment:
                        raise ValidationError(_(
                            "Leave Encashment is disabled for company '%s'. Please enable it in Company / Payroll Settings before creating policies."
                        ) % comp.name)
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'calculation_basis' in vals or 'custom_formula_code' in vals:
            draft_requests = self.env['hds.leave.encashment.request'].search([
                ('policy_id', 'in', self.ids),
                ('state', 'in', ('draft', 'submitted')),
            ])
            if draft_requests:
                draft_requests._compute_projected_amount()
        return res

