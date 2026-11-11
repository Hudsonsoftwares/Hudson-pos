# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
from odoo import api, fields, models, tools, _


class ResCompany(models.Model):
    """Extend company to store default payroll configuration settings."""
    _inherit = 'res.company'

    @api.model
    def _auto_init(self):
        try:
            self.env.cr.execute("""
                ALTER TABLE res_company 
                ADD COLUMN IF NOT EXISTS enable_attendance_threshold BOOLEAN DEFAULT TRUE,
                ADD COLUMN IF NOT EXISTS min_attendance_threshold_days NUMERIC DEFAULT 14.0;
            """)
        except Exception:
            pass
        return super()._auto_init()
        res = super()._auto_init()
        if tools.sql.table_exists(self.env.cr, 'res_company'):
            try:
                with self.env.cr.savepoint():
                    self.env.cr.execute("""
                        ALTER TABLE res_company 
                        ADD COLUMN IF NOT EXISTS enable_attendance_threshold BOOLEAN DEFAULT TRUE,
                        ADD COLUMN IF NOT EXISTS min_attendance_threshold_days NUMERIC DEFAULT 14.0;
                    """)
            except Exception:
                pass
        return res


    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        super()._onchange_parent_id()
        if self.parent_id:
            root = getattr(self.parent_id, 'root_id', self.parent_id) or self.parent_id
            for fname in self._get_company_root_delegated_field_names():
                if fname in self._fields and hasattr(root, fname) and self[fname] != root[fname]:
                    self[fname] = root[fname]

    ytd_reset_date = fields.Selection([
        ('01-01', '1st of January (Calendar Year)'),
        ('04-01', '1st of April (Fiscal Year)'),
        ('07-01', '1st of July'),
        ('10-01', '1st of October'),
    ], string='YTD Reset Date', default='01-01',
       help="Date when Year-To-Date (YTD) accumulator totals reset to zero.")

    send_payslips = fields.Selection([
        ('draft', 'When Draft'),
        ('confirmed', 'When Confirmed'),
        ('paid', 'When Paid'),
        ('manual', 'Manual Only'),
    ], string='Send Payslips to Employees', default='confirmed',
       help="Define when payslips are printed and sent to employees.")

    deferred_time_off = fields.Boolean(
        string='Deferred Time Off',
        default=False,
        help="Postpone time off after payslip validation."
    )
    deferred_time_off_responsible_id = fields.Many2one(
        'res.users',
        string='Deferred Time Off Responsible',
        help="Responsible user for managing deferred time off."
    )
    payrun_accounting = fields.Boolean(
        string='Batch Accounting Entries',
        default=False,
        help="Create consolidated journal entries upon pay run confirmation."
    )
    enable_contract_expiry_notification = fields.Boolean(
        string='Enable Contract Expiry Notification',
        default=True,
        help="Send automated email and in-app notifications when contracts are nearing expiration."
    )
    enable_work_permit_expiry_notification = fields.Boolean(
        string='Enable Work Permit Expiry Notification',
        default=True,
        help="Send automated email and in-app notifications when work permits are nearing expiration."
    )
    expiry_notification_user_ids = fields.Many2many(
        'res.users',
        'company_expiry_notification_user_rel',
        'company_id',
        'user_id',
        string='Expiry Notification HR Recipients',
        help="Specific HR / Management users who should receive in-app and email notifications when contracts or work permits are expiring. If empty, defaults to employee's HR Responsible and Payroll Managers."
    )
    enable_attendance_threshold = fields.Boolean(
        string='Enable Attendance Threshold for Fixed Salary',
        default=True,
        help="When Pay by Attendance is disabled, apply a minimum working days threshold to qualify for full fixed salary."
    )
    min_attendance_threshold_days = fields.Float(
        string='Default Minimum Attendance Days',
        default=14.0,
        help="Default minimum working days an employee must work in a month to qualify for 100% fixed salary when Pay by Attendance is disabled. If worked days fall below this, salary is prorated to actual days worked. If worked days = 0, salary is 0."
    )

    @api.constrains(lambda self: self._get_company_root_delegated_field_names() + ['parent_id'])
    def _check_root_delegated_fields(self):
        for company in self:
            if company.parent_id:
                root = getattr(company.parent_id, 'root_id', company.parent_id) or company.parent_id
                for fname in company._get_company_root_delegated_field_names():
                    if fname in company._fields and hasattr(root, fname) and company[fname] != root[fname]:
                        company[fname] = root[fname]
        return super()._check_root_delegated_fields()

    @api.model_create_multi
    def create(self, vals_list):
        delegated = self._get_company_root_delegated_field_names()
        for vals in vals_list:
            parent_id = vals.get('parent_id') or self.env.context.get('default_parent_id')
            if parent_id:
                vals['parent_id'] = parent_id
                parent = self.browse(parent_id)
                root = getattr(parent, 'root_id', parent) or parent
                for fname in delegated:
                    if fname in self._fields and hasattr(root, fname):
                        vals[fname] = self._fields[fname].convert_to_write(root[fname], root)
        # Strip default_parent_id from context so downstream precommit/chart template hooks don't poison other models (e.g. account.account)
        cleaned_self = self.with_context({k: v for k, v in self.env.context.items() if k != 'default_parent_id'})
        companies = super(ResCompany, cleaned_self).create(vals_list)
        for company in companies:
            if company.country_id:
                structures = self.env['hr.payroll.structure'].search([
                    ('company_id', '=', company.id),
                    ('country_id', '=', False)
                ])
                if structures:
                    structures.write({'country_id': company.country_id.id})
        return companies

    def write(self, vals):
        # Keep subsidiary companies harmonized with root company for all root-delegated fields
        delegated = self._get_company_root_delegated_field_names()
        for company in self:
            parent = company.parent_id or (self.browse(vals['parent_id']) if vals.get('parent_id') else False)
            if parent:
                root = getattr(parent, 'root_id', parent) or parent
                for fname in delegated:
                    if fname in vals and fname in company._fields and hasattr(root, fname):
                        target_val = company._fields[fname].convert_to_write(root[fname], root)
                        if vals[fname] != target_val:
                            vals[fname] = target_val
        cleaned_self = self.with_context({k: v for k, v in self.env.context.items() if k != 'default_parent_id'})
        res = super(ResCompany, cleaned_self).write(vals)
        if 'country_id' in vals and vals['country_id']:
            for company in self:
                structures = self.env['hr.payroll.structure'].search([
                    ('company_id', '=', company.id)
                ])
                if structures:
                    structures.write({'country_id': vals['country_id']})
        if 'min_attendance_threshold_days' in vals or 'enable_attendance_threshold' in vals:
            for company in self:
                domain = [('company_id', '=', company.id)]
                if 'threshold_days_manually_set' in self.env['hr.version']._fields:
                    domain.append(('threshold_days_manually_set', '=', False))
                contracts = self.env['hr.version'].search(domain)
                update_vals = {}
                if 'min_attendance_threshold_days' in vals:
                    update_vals['min_attendance_threshold_days'] = company.min_attendance_threshold_days
                if 'enable_attendance_threshold' in vals:
                    update_vals['enable_attendance_threshold'] = company.enable_attendance_threshold
                if update_vals and contracts:
                    contracts.with_context(sync_from_company=True).write(update_vals)
        return res


class ResConfigSettings(models.TransientModel):
    """Payroll Configuration Settings."""
    _inherit = 'res.config.settings'

    # Notice period fields are inherited from res.company via base hr module:
    # contract_expiration_notice_period
    # work_permit_expiration_notice_period

    enable_contract_expiry_notification = fields.Boolean(
        related='company_id.enable_contract_expiry_notification',
        readonly=False,
        string='Enable Contract Expiry Notification'
    )
    enable_work_permit_expiry_notification = fields.Boolean(
        related='company_id.enable_work_permit_expiry_notification',
        readonly=False,
        string='Enable Work Permit Expiry Notification'
    )
    expiry_notification_user_ids = fields.Many2many(
        related='company_id.expiry_notification_user_ids',
        readonly=False,
        string='HR Notification Recipients'
    )

    ytd_reset_date = fields.Selection(
        related='company_id.ytd_reset_date',
        readonly=False,
        string='YTD Reset Date'
    )
    send_payslips = fields.Selection(
        related='company_id.send_payslips',
        readonly=False,
        string='Send Payslips to Employees'
    )
    deferred_time_off = fields.Boolean(
        related='company_id.deferred_time_off',
        readonly=False,
        string='Deferred Time Off'
    )
    deferred_time_off_responsible_id = fields.Many2one(
        'res.users',
        related='company_id.deferred_time_off_responsible_id',
        readonly=False,
        string='Responsible'
    )
    payrun_accounting = fields.Boolean(
        related='company_id.payrun_accounting',
        readonly=False,
        string='Batch Journal Entries'
    )
    module_account = fields.Boolean(
        string='Payroll Accounting',
        help='Post payroll slips and salary journal entries in accounting.'
    )
    module_hr_attendance = fields.Boolean(
        string='Biometric / Attendance Integration',
        help='Integrate attendance records and worked days with payslip computation.'
    )
    enable_attendance_threshold = fields.Boolean(
        related='company_id.enable_attendance_threshold',
        readonly=False,
        string='Enable Attendance Threshold for Fixed Salary'
    )
    min_attendance_threshold_days = fields.Float(
        related='company_id.min_attendance_threshold_days',
        readonly=False,
        string='Default Minimum Attendance Days'
    )

    def set_values(self):
        super().set_values()
        for record in self:
            company = record.company_id
            if company:
                domain = [('company_id', '=', company.id)]
                if 'threshold_days_manually_set' in self.env['hr.version']._fields:
                    domain.append(('threshold_days_manually_set', '=', False))
                contracts = self.env['hr.version'].search(domain)
                if contracts:
                    contracts.with_context(sync_from_company=True).write({
                        'min_attendance_threshold_days': company.min_attendance_threshold_days,
                        'enable_attendance_threshold': company.enable_attendance_threshold,
                    })

    def action_check_and_notify_expirations(self):
        """Action button to trigger expiry check on demand from Settings UI."""
        counts = self.env['hr.employee'].notify_expiring_contract_work_permit()
        c_count = counts.get('contract_notified_count', 0)
        p_count = counts.get('permit_notified_count', 0)
        total = c_count + p_count
        msg = _(
            "Expiry Check Completed: %s contract notification(s) and %s work permit notification(s) processed.",
            c_count, p_count
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Automated Expiry Notifications"),
                'message': msg,
                'type': 'success' if total > 0 else 'info',
                'sticky': False,
            }
        }

