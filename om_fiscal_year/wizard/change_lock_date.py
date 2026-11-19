from odoo import models, fields, api, SUPERUSER_ID, _
from odoo.exceptions import UserError

LOCK_DATE_FIELDS = ('hard_lock_date', 'fiscalyear_lock_date', 'purchase_lock_date', 'sale_lock_date', 'tax_lock_date')


class ChangeLockDate(models.TransientModel):
    _name = 'change.lock.date'
    _description = 'Change Lock Date'

    company_id = fields.Many2one(
        'res.company', string="Company",
        required=True, default=lambda self: self.env.company
    )
    # The lock dates are those of the selected company: changing the company reloads them, so that the dates
    # of a company are never written onto another one.
    tax_lock_date = fields.Date(
        string="Tax Return Lock Date", compute='_compute_lock_dates', store=True, readonly=False, precompute=True,
        help="No users can edit journal entries related to a tax prior and inclusive of this date.")
    sale_lock_date = fields.Date(
        string='Sales Lock Date', compute='_compute_lock_dates', store=True, readonly=False, precompute=True,
        help='Prevents creation and modification of entries in sales journals up to the defined date inclusive.'
    )
    purchase_lock_date = fields.Date(
        string='Purchase Lock date', compute='_compute_lock_dates', store=True, readonly=False, precompute=True,
        help='Prevents creation and modification of entries in purchase journals up to the defined date inclusive.'
    )
    hard_lock_date = fields.Date(
        string='Hard Lock Date', compute='_compute_lock_dates', store=True, readonly=False, precompute=True,
        help='Like the "Global Lock Date", but no exceptions are possible.'
    )
    fiscalyear_lock_date = fields.Date(
        string='Lock Date for All Users', compute='_compute_lock_dates', store=True, readonly=False,
        precompute=True,
        help='No users, including Advisers, can edit accounts prior to and inclusive of '
             'this date. Use it for fiscal year locking.'
    )

    @api.depends('company_id')
    def _compute_lock_dates(self):
        for wizard in self:
            company = wizard.company_id.sudo()
            for field_name in LOCK_DATE_FIELDS:
                wizard[field_name] = company[field_name]

    def update_lock_date(self):
        self.ensure_one()
        has_manager_group = self.env.user.has_group('account.group_account_manager')
        if not (has_manager_group or self.env.uid == SUPERUSER_ID):
            raise UserError(_("You Are Not Allowed To Perform This Operation"))
        if self.env.uid != SUPERUSER_ID and self.company_id not in self.env.user.company_ids:
            raise UserError(_("You cannot change the lock dates of another company."))
        company = self.company_id.sudo()
        # only the lock dates changed in the wizard are written: the others (the hard lock date in particular,
        # which cannot be lowered) stay as they are on the company
        values = {
            field_name: self[field_name]
            for field_name in LOCK_DATE_FIELDS
            if self[field_name] != company[field_name]
        }
        if values:
            # sudo() is required because setting lock dates writes on res.company,
            # which accounting managers are not allowed to write on.
            company.write(values)
        return True
