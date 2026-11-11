# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ---------------------------------------------------------
    # Personal Information & Preferences
    # ---------------------------------------------------------
    is_disabled = fields.Boolean(
        string='Disabled?',
        default=False,
        help="Generic demographic/administrative indicator if employee is a person with disabilities."
    )
    payslip_lang_id = fields.Many2one(
        'res.lang',
        string='Payslip Language',
        help="Preferred language for payslip display and generation."
    )

    # ---------------------------------------------------------
    # Citizenship
    # ---------------------------------------------------------
    is_non_resident = fields.Boolean(
        string='Non-resident?',
        default=False,
        help="Residency classification indicator for administrative and HR profile purposes."
    )

    # ---------------------------------------------------------
    # Visa & Work Permit
    # ---------------------------------------------------------
    work_permit_expiry_date = fields.Date(
        string='Expires On',
        help="Expiration date of the employee's work permit."
    )

    # ---------------------------------------------------------
    # Family Information
    # ---------------------------------------------------------
    spouse_legal_name = fields.Char(
        string='Spouse Legal Name',
        help="Legal full name of the employee's spouse."
    )
    spouse_birthdate = fields.Date(
        string='Spouse Birthdate',
        help="Date of birth of the employee's spouse."
    )
    child_residing_in_hostel = fields.Integer(
        string='Child Residing in hostel',
        help="Number of children residing in hostel."
    )

    # ---------------------------------------------------------
    # Employee Documents
    # ---------------------------------------------------------
    sim_card_copy = fields.Binary(
        string='SIM Card Copy',
        attachment=True,
        help="Attached digital copy of the employee's SIM Card."
    )
    sim_card_copy_filename = fields.Char(string='SIM Card Copy Filename')

    internet_subscription_invoice = fields.Binary(
        string='Internet Subscription Invoice',
        attachment=True,
        help="Attached digital copy of the employee's Internet Subscription Invoice."
    )
    internet_subscription_invoice_filename = fields.Char(string='Internet Subscription Invoice Filename')

    @api.constrains('spouse_birthdate')
    def _check_spouse_birthdate(self):
        today = fields.Date.today()
        for employee in self:
            if employee.spouse_birthdate and employee.spouse_birthdate > today:
                raise ValidationError(_("Spouse Birthdate cannot be in the future."))
                
    # ---------------------------------------------------------
    # Appraisal Information
    # ---------------------------------------------------------
    next_appraisal_date = fields.Date(
        string='Next Appraisal Date',
        help="Date of the next appraisal"
    )

    # ---------------------------------------------------------
    # Approvers
    # ---------------------------------------------------------
    expense_manager_id = fields.Many2one(
        'res.users',
        string='Expense',
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help="User responsible for approving employee expenses."
    )
    timesheet_manager_id = fields.Many2one(
        'res.users',
        string='Timesheet',
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help="User responsible for approving employee timesheets."
    )

    # ---------------------------------------------------------
    # Application Settings
    # ---------------------------------------------------------
    employee_hourly_cost = fields.Monetary(
        string='Hourly Cost',
        currency_field='currency_id',
        default=0.0,
        help="Employee's hourly cost used in timesheet and project costing."
    )
    employee_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Distribution',
        help="Analytic account for employee cost allocation."
    )

    # ---------------------------------------------------------
    # Export
    # ---------------------------------------------------------
    export_external_code = fields.Char(
        string='External Code',
        help="Code used in work entry exports.",
        placeholder="Code used in work entry exports"
    )
