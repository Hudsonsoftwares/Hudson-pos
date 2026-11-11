from datetime import date, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountExecutiveSummaryWizard(models.TransientModel):
    """
    Executive Summary — one-page KPI snapshot for management reporting.
    Shows Revenue, Expenses, Net Profit, Cash Position, AR, AP,
    and key ratios (Current Ratio, Quick Ratio, Gross Margin, Net Margin).
    Optionally includes period comparison.
    """
    _name = 'account.executive.summary.wizard'
    _description = 'Executive Summary Report'

    date_from = fields.Date(
        string='Period From',
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Period To',
        required=True,
        default=lambda self: date.today(),
    )
    compare_date_from = fields.Date(string='Comparison Period From')
    compare_date_to = fields.Date(string='Comparison Period To')
    enable_comparison = fields.Boolean(string='Enable Period Comparison')
    target_move = fields.Selection(
        [('posted', 'All Posted Entries'), ('all', 'All Entries')],
        string='Target Moves',
        required=True,
        default='posted',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    # --- UI State ---
    state = fields.Selection([('choose', 'Choose Parameters'), ('get', 'View Report')], default='choose')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    # --- KPI Fields (Current Period) ---
    revenue = fields.Monetary(string='Revenue', currency_field='currency_id')
    other_income = fields.Monetary(string='Other Income', currency_field='currency_id')
    cogs = fields.Monetary(string='Cost of Goods Sold', currency_field='currency_id')
    opex = fields.Monetary(string='Operating Expenses', currency_field='currency_id')
    total_expenses = fields.Monetary(string='Total Expenses', currency_field='currency_id')
    gross_profit = fields.Monetary(string='Gross Profit', currency_field='currency_id')
    net_profit = fields.Monetary(string='Net Profit', currency_field='currency_id')
    
    cash = fields.Monetary(string='Bank & Cash', currency_field='currency_id')
    ar = fields.Monetary(string='Receivables', currency_field='currency_id')
    ap = fields.Monetary(string='Payables', currency_field='currency_id')
    current_assets = fields.Monetary(string='Current Assets', currency_field='currency_id')
    current_liabilities = fields.Monetary(string='Current Liabilities', currency_field='currency_id')
    equity = fields.Monetary(string='Total Equity', currency_field='currency_id')
    
    bank_closing_balance = fields.Monetary(string='Bank Closing Balance', currency_field='currency_id')
    cash_surplus = fields.Monetary(string='Cash Surplus', currency_field='currency_id')
    
    current_ratio = fields.Float(string='Current Ratio')
    quick_ratio = fields.Float(string='Quick Ratio')
    gross_margin = fields.Float(string='Gross Margin (%)')
    net_margin = fields.Float(string='Net Margin (%)')
    roi = fields.Float(string='Return on Investment (%)')

    report_html = fields.Html(string="Report HTML")

    def _get_journal_clause(self):
        """Restrict to the journals of the selected Multi Ledgers (passed in context)."""
        journal_ids = self.env.context.get('report_journal_ids')
        if journal_ids:
            return "AND aml.journal_id IN %s", (tuple(journal_ids),)
        return '', ()

    def _get_period_sum(self, account_types, df, dt, cid, state):
        """Sum of (debit-credit) for account types in a period."""
        state_clause = "AND aml.parent_state = 'posted'" if state == 'posted' else "AND aml.parent_state IN ('draft', 'posted')"
        journal_clause, journal_params = self._get_journal_clause()
        query = f"""
            SELECT COALESCE(SUM(aml.debit - aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.account_type IN %s
              AND aml.date >= %s AND aml.date <= %s
              AND aml.company_id = %s
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
              {journal_clause}
        """
        self.env.cr.execute(query, (tuple(account_types), df, dt, cid) + journal_params)
        result = self.env.cr.fetchone()
        return result[0] if result else 0.0

    def _get_period_cash_flow(self, df, dt, cid, state):
        """Returns (cash_received, cash_spent) as positive floats."""
        state_clause = "AND aml.parent_state = 'posted'" if state == 'posted' else "AND aml.parent_state IN ('draft', 'posted')"
        journal_clause, journal_params = self._get_journal_clause()
        query = f"""
            SELECT COALESCE(SUM(aml.debit), 0.0), COALESCE(SUM(aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.account_type = 'asset_cash'
              AND aml.date >= %s AND aml.date <= %s
              AND aml.company_id = %s
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
              {journal_clause}
        """
        self.env.cr.execute(query, (df, dt, cid) + journal_params)
        result = self.env.cr.fetchone()
        return result[0] if result else 0.0, result[1] if result else 0.0

    def _get_balance_as_of(self, account_types, as_of, cid, state):
        """Cumulative debit-credit balance up to as_of date."""
        state_clause = "AND aml.parent_state = 'posted'" if state == 'posted' else "AND aml.parent_state IN ('draft', 'posted')"
        journal_clause, journal_params = self._get_journal_clause()
        query = f"""
            SELECT COALESCE(SUM(aml.debit - aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.account_type IN %s
              AND aml.date <= %s
              AND aml.company_id = %s
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
              {journal_clause}
        """
        self.env.cr.execute(query, (tuple(account_types), as_of, cid) + journal_params)
        result = self.env.cr.fetchone()
        return result[0] if result else 0.0

    def _compute_kpis(self, df, dt, cid, state):
        """Compute all KPIs for a given period."""
        revenue = -self._get_period_sum(['income'], df, dt, cid, state)
        other_income = -self._get_period_sum(['income_other'], df, dt, cid, state)
        cogs = self._get_period_sum(['expense_direct_cost'], df, dt, cid, state)
        opex = self._get_period_sum(['expense', 'expense_depreciation'], df, dt, cid, state)
        other_expenses = self._get_period_sum(['expense_other'], df, dt, cid, state)
        total_expenses = cogs + opex + other_expenses
        gross_profit = revenue - cogs
        net_profit = revenue + other_income - total_expenses

        # Balance sheet KPIs as of date_to
        cash = self._get_balance_as_of(['asset_cash'], dt, cid, state)
        ar = self._get_balance_as_of(['asset_receivable'], dt, cid, state)
        current_assets = self._get_balance_as_of(
            ['asset_receivable', 'asset_cash', 'asset_current', 'asset_prepayments'], dt, cid, state
        )
        current_liabilities = -self._get_balance_as_of(
            ['liability_payable', 'liability_credit_card', 'liability_current'], dt, cid, state
        )
        ap = -self._get_balance_as_of(['liability_payable', 'liability_credit_card'], dt, cid, state)
        equity = -self._get_balance_as_of(['equity', 'equity_unaffected'], dt, cid, state)

        # Cash flows
        cash_received, cash_spent = self._get_period_cash_flow(df, dt, cid, state)
        # Opening balance is the balance at the end of the day before the period
        cash_at_start = self._get_balance_as_of(['asset_cash'], df - timedelta(days=1), cid, state)
        cash_surplus = cash - cash_at_start

        # Ratios & Position Metrics
        current_ratio = (current_assets / current_liabilities) if current_liabilities else 0.0
        gross_margin = (gross_profit / revenue * 100) if revenue else 0.0
        net_margin = (net_profit / revenue * 100) if revenue else 0.0
        total_assets = self._get_balance_as_of(
            ['asset_receivable', 'asset_cash', 'asset_current', 'asset_prepayments', 'asset_non_current', 'asset_fixed'], dt, cid, state
        )
        total_liabilities = -self._get_balance_as_of(
            ['liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current'], dt, cid, state
        )
        roi = (net_profit / total_assets * 100) if total_assets else 0.0

        # Scale by the actual period length, not a full year
        period_days = (dt - df).days + 1
        avg_debtors_days = (ar / revenue) * period_days if revenue else 0.0
        avg_creditors_days = (ap / cogs) * period_days if cogs else 0.0
        short_term_cash_forecast = cash + ar - ap

        return {
            'cash_received': cash_received,
            'cash_spent': cash_spent,
            'cash_surplus': cash_surplus,
            'cash': cash,
            'revenue': revenue,
            'cogs': cogs,
            'gross_profit': gross_profit,
            'opex': opex,
            'net_profit': net_profit,
            'ar': ar,
            'ap': ap,
            'net_assets': total_assets - total_liabilities,
            'gross_margin': gross_margin,
            'net_margin': net_margin,
            'roi': roi,
            'avg_debtors_days': avg_debtors_days,
            'avg_creditors_days': avg_creditors_days,
            'short_term_cash_forecast': short_term_cash_forecast,
            'current_ratio': current_ratio,
        }

    def _generate_html(self, data):
        """Generates the dark themed HTML string for the report."""
        currency = self.env.company.currency_id

        def format_monetary(amount):
            if amount < 0:
                # E.g. ₹ -21.64
                return f'<span style="color:#d9534f;">{currency.symbol} {amount:,.2f}</span>'
            return f'{currency.symbol} {amount:,.2f}'

        def format_percent(val):
            return f"{val:,.1f}%"

        def format_days(val):
            return f"{val:,.1f}"

        html = f"""
        <div style="background-color: #212529; color: #f8f9fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; padding: 20px; border-radius: 8px;">
            
            <div style="max-width: 800px; margin: 0 auto; background-color: #2c3136; border-radius: 4px; border: 1px solid #444c54;">
                
                <!-- Cash Section -->
                <div style="background-color: #3f474f; padding: 8px 15px; font-weight: bold; border-bottom: 1px solid #444c54; border-top-left-radius: 4px; border-top-right-radius: 4px;">Cash</div>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Cash received</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(data['cash_received'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Cash spent</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(-data['cash_spent'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Cash surplus</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(data['cash_surplus'])}</td></tr>
                    <tr><td style="padding: 8px 15px;">Closing bank balance</td><td style="padding: 8px 15px; text-align: right;">{format_monetary(data['cash'])}</td></tr>
                </table>

                <!-- Profitability Section -->
                <div style="background-color: #3f474f; padding: 8px 15px; font-weight: bold; border-bottom: 1px solid #444c54; border-top: 1px solid #444c54; color: #17a2b8;">Profitability</div>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Revenue</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(data['revenue'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Cost of Revenue</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(data['cogs'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Gross profit</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(data['gross_profit'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Expenses</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(data['opex'])}</td></tr>
                    <tr><td style="padding: 8px 15px;">Net Profit</td><td style="padding: 8px 15px; text-align: right;">{format_monetary(data['net_profit'])}</td></tr>
                </table>

                <!-- Balance Sheet Section -->
                <div style="background-color: #3f474f; padding: 8px 15px; font-weight: bold; border-bottom: 1px solid #444c54; border-top: 1px solid #444c54; color: #17a2b8;">Balance Sheet</div>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Receivables</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(data['ar'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Payables</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(-data['ap'])}</td></tr>
                    <tr><td style="padding: 8px 15px;">Net assets</td><td style="padding: 8px 15px; text-align: right;">{format_monetary(data['net_assets'])}</td></tr>
                </table>

                <!-- Performance Section -->
                <div style="background-color: #3f474f; padding: 8px 15px; font-weight: bold; border-bottom: 1px solid #444c54; border-top: 1px solid #444c54;">Performance</div>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Gross profit margin (gross profit / operating income)</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_percent(data['gross_margin'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Net profit margin (net profit / revenue)</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_percent(data['net_margin'])}</td></tr>
                    <tr><td style="padding: 8px 15px;">Return on investments (net profit / assets)</td><td style="padding: 8px 15px; text-align: right;">{format_percent(data['roi'])}</td></tr>
                </table>

                <!-- Position Section -->
                <div style="background-color: #3f474f; padding: 8px 15px; font-weight: bold; border-bottom: 1px solid #444c54; border-top: 1px solid #444c54;">Position</div>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Average debtors days</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_days(data['avg_debtors_days'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Average creditors days</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_days(data['avg_creditors_days'])}</td></tr>
                    <tr><td style="padding: 8px 15px; border-bottom: 1px solid #444c54;">Short-term cash forecast</td><td style="padding: 8px 15px; text-align: right; border-bottom: 1px solid #444c54;">{format_monetary(data['short_term_cash_forecast'])}</td></tr>
                    <tr><td style="padding: 8px 15px;">Current assets to liabilities</td><td style="padding: 8px 15px; text-align: right;">{format_days(data['current_ratio'])}</td></tr>
                </table>
            </div>
        </div>
        """
        return html

    def _compute_summary_data(self):
        self.ensure_one()
        # company_id can come from client data and is used in raw SQL
        if self.company_id not in self.env.companies:
            raise UserError(_("You are not allowed to access this company's data."))
        cid = self.company_id.id
        state = self.target_move
        current = self._compute_kpis(self.date_from, self.date_to, cid, state)

        comparison = None
        if self.enable_comparison and self.compare_date_from and self.compare_date_to:
            comparison = self._compute_kpis(self.compare_date_from, self.compare_date_to, cid, state)

        return {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company': self.company_id.id,
            'target_move': state,
            'current': current,
            'comparison': comparison,
            'compare_date_from': self.compare_date_from,
            'compare_date_to': self.compare_date_to,
        }

    def action_generate(self):
        """Generate inline executive summary."""
        self.ensure_one()
        
        data = self.read()[0]
        data['form'] = data.copy()
        
        return {
            'name': 'Executive Summary',
            'type': 'ir.actions.client',
            'tag': 'hudson_dynamic_reports.dynamic_report',
            'params': {
                'model_name': 'account.executive.summary.wizard',
                'wizard_id': self.id,
                'data': data
            }
        }

    def action_recompute(self):
        """Go back to parameter selection."""
        self.ensure_one()
        self.write({'state': 'choose'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.executive.summary.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print_report(self):
        self.ensure_one()
        data = self._compute_summary_data()
        return self.env.ref(
            'hudson_accounting_enhancements.action_report_executive_summary'
        ).report_action(self, data={'form': data})

    def check_report(self):
        return self.action_print_report()
