from datetime import date, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountAnnualReportWizard(models.TransientModel):
    """
    Annual Report wizard — combines the Balance Sheet and P&L for a full fiscal year
    into a single comprehensive financial summary document.
    """
    _name = 'account.annual.report.wizard'
    _description = 'Annual Financial Report'

    fiscal_year = fields.Integer(
        string='Fiscal Year',
        required=True,
        default=lambda self: date.today().year - 1,
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: date.today().replace(month=1, day=1, year=date.today().year - 1),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=lambda self: date.today().replace(month=12, day=31, year=date.today().year - 1),
    )
    target_move = fields.Selection(
        [('posted', 'All Posted Entries'), ('all', 'All Entries')],
        string='Target Moves',
        required=True,
        default='posted',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    @api.onchange('fiscal_year')
    def _onchange_fiscal_year(self):
        if self.fiscal_year:
            self.date_from = date(self.fiscal_year, 1, 1)
            self.date_to = date(self.fiscal_year, 12, 31)

    @staticmethod
    def _clean_zero(val):
        if val is None or val is False:
            return 0.0
        if isinstance(val, (int, float)):
            return 0.0 if abs(val) < 0.005 else val
        elif isinstance(val, dict):
            return {k: AccountAnnualReportWizard._clean_zero(v) for k, v in val.items()}
        elif isinstance(val, (list, tuple)):
            return [AccountAnnualReportWizard._clean_zero(v) for v in val]
        return val

    def _get_balance(self, account_types, date_from, date_to, company_id, state):
        """Get net debit-credit balance for given account types in a period."""
        state_clause = "AND aml.parent_state = 'posted'" if state == 'posted' else "AND aml.parent_state IN ('draft', 'posted')"
        query = f"""
            SELECT COALESCE(SUM(aml.debit - aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.account_type IN %s
              AND aml.date >= %s
              AND aml.date <= %s
              AND aml.company_id = %s
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
        """
        self.env.cr.execute(query, (tuple(account_types), date_from, date_to, company_id))
        result = self.env.cr.fetchone()
        val = result[0] if (result and result[0] is not None) else 0.0
        return 0.0 if abs(val) < 0.005 else val

    def _get_cumulative_balance(self, account_types, as_of_date, company_id, state):
        """Get cumulative balance up to a date for BS items."""
        state_clause = "AND aml.parent_state = 'posted'" if state == 'posted' else "AND aml.parent_state IN ('draft', 'posted')"
        query = f"""
            SELECT COALESCE(SUM(aml.debit - aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.account_type IN %s
              AND aml.date <= %s
              AND aml.company_id = %s
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
        """
        self.env.cr.execute(query, (tuple(account_types), as_of_date, company_id))
        result = self.env.cr.fetchone()
        val = result[0] if (result and result[0] is not None) else 0.0
        return 0.0 if abs(val) < 0.005 else val

    def _compute_annual_data(self):
        self.ensure_one()
        if self.company_id and self.company_id not in self.env.companies:
            raise UserError(_("You cannot generate an Annual Report for a company you are not currently logged into (%s).") % self.company_id.name)
        if self.date_from > self.date_to:
            raise UserError(_('Date From must be before Date To.'))

        cid = self.company_id.id
        df = self.date_from
        dt = self.date_to
        st = self.target_move

        # ── P&L Items (period movements) ──
        revenue = -self._get_balance(['income'], df, dt, cid, st)
        other_income = -self._get_balance(['income_other'], df, dt, cid, st)
        cogs = self._get_balance(['expense_direct_cost'], df, dt, cid, st)
        operating_expenses = self._get_balance(['expense'], df, dt, cid, st)
        depreciation = self._get_balance(['expense_depreciation'], df, dt, cid, st)

        other_expenses = self._get_balance(['expense_other'], df, dt, cid, st)

        gross_profit = revenue - cogs
        operating_profit = gross_profit - operating_expenses - depreciation
        net_profit = operating_profit + other_income - other_expenses

        # ── Balance Sheet Items (cumulative as of date_to) ──
        # Assets
        current_assets = self._get_cumulative_balance(
            ['asset_receivable', 'asset_cash', 'asset_current', 'asset_prepayments'], dt, cid, st
        )
        noncurrent_assets = self._get_cumulative_balance(
            ['asset_non_current', 'asset_fixed'], dt, cid, st
        )
        total_assets = current_assets + noncurrent_assets

        # Liabilities
        current_liabilities = -self._get_cumulative_balance(
            ['liability_payable', 'liability_credit_card', 'liability_current'], dt, cid, st
        )
        noncurrent_liabilities = -self._get_cumulative_balance(
            ['liability_non_current'], dt, cid, st
        )
        total_liabilities = current_liabilities + noncurrent_liabilities

        # Equity
        share_capital = -self._get_cumulative_balance(['equity'], dt, cid, st)
        # Unclosed P&L of earlier periods belongs to retained earnings
        retained_earnings = -self._get_cumulative_balance(['equity_unaffected'], dt, cid, st)             - self._get_cumulative_balance(['income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost'], df - timedelta(days=1), cid, st)
        total_equity = share_capital + retained_earnings + net_profit

        data = {
            'fiscal_year': self.fiscal_year,
            'date_from': df,
            'date_to': dt,
            'company': self.company_id.id,
            'company_id': self.company_id.id,
            'target_move': st,
            # P&L
            'revenue': revenue,
            'other_income': other_income,
            'cogs': cogs,
            'gross_profit': gross_profit,
            'operating_expenses': operating_expenses,
            'depreciation': depreciation,
            'operating_profit': operating_profit,
            'net_profit': net_profit,
            # BS
            'current_assets': current_assets,
            'noncurrent_assets': noncurrent_assets,
            'total_assets': total_assets,
            'current_liabilities': current_liabilities,
            'noncurrent_liabilities': noncurrent_liabilities,
            'total_liabilities': total_liabilities,
            'share_capital': share_capital,
            'retained_earnings': retained_earnings,
            'total_equity': total_equity,
        }
        return self._clean_zero(data)

    def action_print_report(self):
        """ The annual report template is bound to account.annual.report (prior year,
        aged balances, report name): print through such a record so the PDF gets all
        of its data instead of browsing wizard ids as annual reports. """
        self.ensure_one()
        self._compute_annual_data()  # validates the company / parameters
        report = self.env['account.annual.report'].create({
            'name': _("Annual Report %s", self.date_to.year),
            'date_from': self.date_from,
            'date_to': self.date_to,
            'target_move': self.target_move,
            'company_id': self.company_id.id,
        })
        return report.action_print_report()

    def check_report(self):
        return self.action_print_report()
