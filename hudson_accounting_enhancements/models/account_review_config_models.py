from odoo import api, fields, models, _

class AccountWorkingFile(models.Model):
    _name = "account.working.file"
    _description = "Audit Working File"
    _order = "date_to desc, id desc"

    name = fields.Char(string="Working File Reference", required=True, default=lambda self: _("New Audit Cycle"))
    date_from = fields.Date(string="Start Date", default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date(string="End Date", default=fields.Date.context_today)
    company_id = fields.Many2one("res.company", string="Company", required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one("res.users", string="Auditor / Responsible", default=lambda self: self.env.user)
    state = fields.Selection([
        ("draft", "To Review"),
        ("in_progress", "Under Review"),
        ("validated", "Validated"),
        ("closed", "Closed")
    ], string="Status", default="draft", required=True)
    description = fields.Text(string="Audit Objectives & Notes")


class AccountTaxUnit(models.Model):
    _name = "account.tax.unit"
    _description = "Tax Unit"

    name = fields.Char(string="Tax Unit Name", required=True)
    country_id = fields.Many2one("res.country", string="Country", required=True, default=lambda self: self.env.company.country_id)
    vat = fields.Char(string="VAT Number")
    main_company_id = fields.Many2one("res.company", string="Main Company", required=True, default=lambda self: self.env.company)
    company_ids = fields.Many2many("res.company", string="Member Companies", default=lambda self: self.env.company)


class AccountHorizontalGroup(models.Model):
    _name = "account.horizontal.group"
    _description = "Accounting Horizontal Report Group"

    name = fields.Char(string="Group Name", required=True)
    code = fields.Char(string="Code")
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company)


class AccountFiscalCategory(models.Model):
    _name = "account.fiscal.category"
    _description = "Fiscal Category"

    name = fields.Char(string="Category Name", required=True)
    code = fields.Char(string="Code")
    description = fields.Text(string="Description")


class AccountReturnType(models.Model):
    _name = "account.return.type"
    _description = "Tax Return Type"

    name = fields.Char(string="Return Type", required=True)
    code = fields.Char(string="Code")
    country_id = fields.Many2one("res.country", string="Country", default=lambda self: self.env.company.country_id)
    periodicity = fields.Selection([
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("yearly", "Yearly")
    ], string="Periodicity", default="monthly")


class AccountOnlineSync(models.Model):
    _name = "account.online.sync"
    _description = "Online Banking Synchronization"

    name = fields.Char(string="Connection Name", required=True)
    journal_id = fields.Many2one("account.journal", string="Bank Journal", domain=[("type", "=", "bank")])
    status = fields.Selection([
        ("connected", "Connected"),
        ("disconnected", "Disconnected"),
        ("error", "Action Required")
    ], string="Sync Status", default="connected")
    last_sync = fields.Datetime(string="Last Synchronization", default=fields.Datetime.now)

    @api.model
    def _register_hook(self):
        super()._register_hook()
        for xml_id in [
            'l10n_in.account_reports_in_statements_menu',
            'om_account_accountant.menu_review_moves_to_review',
            'om_account_accountant.menu_review_moves_unposted',
            'om_account_accountant.menu_review_reconciliation',
            'om_account_accountant.menu_review_regularization',
            'om_account_accountant.menu_finance_entries_accounting_journals',
            'om_account_accountant.menu_accounting_bank_and_cash',
            'accounting_pdf_reports.menu_finance_entries_accounting_ledgers',
            'om_recurring_payments.menu_recurring_payment',
            'om_recurring_payments.menu_move_auto_post',
            'om_account_cash_forecast.menu_cash_forecast_item',
            'om_account_reconcile.menu_reconciliation',
            'om_fiscal_year.menu_account_period_closing',
            'om_fiscal_year.menu_fiscal_year_closing',
            'om_currency_revaluation.menu_currency_revaluation',
        ]:
            menu = self.env.ref(xml_id, raise_if_not_found=False)
            if menu and menu.active:
                menu.sudo().write({'active': False})

        # Ensure PAN Entity is under Transactions with sequence 20
        pan_menu = self.env.ref('l10n_in.menu_l10n_in_pan_entity', raise_if_not_found=False)
        trans_menu = self.env.ref('account.account_transactions_menu', raise_if_not_found=False)
        if pan_menu and trans_menu:
            pan_menu.sudo().write({
                'parent_id': trans_menu.id,
                'sequence': 20,
                'active': True,
            })

