from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from datetime import timedelta, date, datetime
from dateutil.relativedelta import relativedelta
import uuid
import logging

_logger = logging.getLogger(__name__)

class HudsonDynamicReport(models.AbstractModel):
    _name = "hudson.dynamic.report"
    _description = "Dynamic Report Endpoint"

    @api.model
    def get_installed_integrations(self):
        """Which entries the gear menu next to the report title offers.

        Each entry is provided by a bridge module (hudson_accounting_dms,
        hudson_accounting_knowledge), so look for the bridge's wizard rather than
        the base app: with only the base app installed the wizard doesn't exist.
        The user must also be able to create what the entry produces.
        """
        def available(wizard_model, target_model, operation):
            if wizard_model not in self.env or target_model not in self.env:
                return False
            return self.env[target_model].has_access(operation)

        return {
            'dms': available('hudson.report.export.dms.wizard', 'dms.file', 'create'),
            'knowledge': available('hudson.report.export.knowledge.wizard', 'knowledge.management.article', 'write'),
        }

    @api.model
    def action_open_statement(self, partner_id):
        partner = self.env['res.partner'].browse(partner_id)
        partner_title = partner.name if partner.exists() else "Partner"

        # Use a standard act_window so Odoo's action manager properly stacks it on top
        # of the Aged Report — browser Back will correctly return to the Aged Report.
        from odoo import fields as F
        today = F.Date.context_today(self)
        return {
            'name': f"Partner Ledger - {partner_title}",
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [
                ('partner_id', '=', partner_id),
                ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
            ],
            'context': {
                'search_default_group_by_move': 1,
                'default_partner_id': partner_id,
            },
        }

    @api.model
    def _get_query_components(self, model_name, domain):
        """Build FROM and WHERE clauses and parameters compatible across all Odoo versions."""
        model = self.env[model_name]
        if hasattr(model, '_where_calc'):
            query = model._where_calc(domain)
        else:
            query = model._search(domain)

        from_clause = getattr(query, 'from_clause', None)
        where_clause = getattr(query, 'where_clause', None)

        from_string = ""
        where_string = ""
        where_params = []

        if hasattr(from_clause, '_sql_tuple'):
            from_string, from_params, _ = from_clause._sql_tuple
            if where_clause and hasattr(where_clause, '_sql_tuple'):
                where_string, w_params, _ = where_clause._sql_tuple
            else:
                where_string, w_params = "", ()
            where_params = list(from_params) + list(w_params)
        elif hasattr(from_clause, 'code'):
            from_string = from_clause.code
            where_string = where_clause.code if where_clause else ""
            where_params = list(where_clause.params or []) if where_clause else []
        elif isinstance(from_clause, (tuple, list)):
            from_string, from_params = from_clause
            where_string, w_params = where_clause if where_clause else ("", ())
            where_params = list(from_params) + list(w_params)
        else:
            from_string = str(from_clause) if from_clause else ""
            where_string = str(where_clause) if where_clause else ""
            where_params = []

        return from_string, where_string, where_params

    @api.model
    def _compute_percentage_comparison(self, result, form_data, is_pl=False, is_bs=False, pl_base_map=None, cmp_periods_info=None):
        """Universal percentage comparison calculator supporting Balance Sheet, P&L, Annual Report, Trial Balance, etc."""
        if not result or not result.get('lines'):
            return

        lines = result['lines']
        columns = result.setdefault('columns', [])

        if form_data.get('comparison') == 'percentage':
            if any(c.get('field') == 'percentage_val' for c in columns):
                return

            percentage_base = form_data.get('percentage_base', 'revenue')
            base_labels = {
                'revenue': _('Revenue'),
                'costs_of_revenue': _('Costs of Revenue'),
                'gross_profit': _('Gross Profit'),
                'operating_expenses': _('Operating Expenses'),
                'operating_income': _('Operating Income (or Loss)'),
                'other_income': _('Other Income'),
                'other_expenses': _('Other Expenses'),
                'net_profit': _('Net Profit'),
                'allocations': _('Allocations and Withdrawals'),
                'total_assets': _('Total Assets'),
                'current_assets': _('Current Assets'),
                'bank_and_cash': _('Bank and Cash'),
                'receivables': _('Receivables'),
                'prepayments': _('Prepayments'),
                'fixed_assets': _('Fixed Assets'),
                'non_current_assets': _('Non-current Assets'),
                'total_liabilities': _('Total Liabilities'),
                'current_liabilities': _('Current Liabilities'),
                'payables': _('Payables'),
                'non_current_liabilities': _('Non-current Liabilities'),
                'total_equity': _('Total Equity'),
                'retained_earnings': _('Retained Earnings'),
                'total_liabilities_equity': _('Total Liabilities & Equity'),
                'total_debit': _('Total Debit'),
                'total_credit': _('Total Credit'),
                'total_balance': _('Total Balance'),
            }

            base_name = base_labels.get(percentage_base, percentage_base.replace('_', ' ').title())
            base_balance = 0.0

            # 1. Check P&L calculated section map if available
            if pl_base_map and percentage_base in pl_base_map:
                base_balance = abs(pl_base_map[percentage_base])

            # 2. Specific matching against current report lines
            if not base_balance:
                if percentage_base in ('total_assets', 'assets'):
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        fid = str(fl.get('id') or '').lower()
                        if ('asset' in fn or 'asset' in fid) and fl.get('level') in (1, 2):
                            bal = abs(fl.get('balance', 0.0))
                            if bal > base_balance:
                                base_balance = bal
                elif percentage_base in ('current_assets',):
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        if 'current asset' in fn and fl.get('level') in (1, 2):
                            base_balance = max(base_balance, abs(fl.get('balance', 0.0)))
                elif percentage_base in ('bank_and_cash', 'bank', 'cash'):
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        if 'bank' in fn or 'cash' in fn:
                            base_balance = max(base_balance, abs(fl.get('balance', 0.0)))
                elif percentage_base in ('receivables', 'receivable'):
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        if 'receivable' in fn:
                            base_balance = max(base_balance, abs(fl.get('balance', 0.0)))
                elif percentage_base in ('total_liabilities', 'liabilities'):
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        fid = str(fl.get('id') or '').lower()
                        if ('liabilit' in fn or 'liabilit' in fid) and fl.get('level') in (1, 2):
                            bal = abs(fl.get('balance', 0.0))
                            if bal > base_balance:
                                base_balance = bal
                elif percentage_base in ('current_liabilities',):
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        if 'current liabilit' in fn and fl.get('level') in (1, 2):
                            base_balance = max(base_balance, abs(fl.get('balance', 0.0)))
                elif percentage_base in ('payables', 'payable'):
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        if 'payable' in fn:
                            base_balance = max(base_balance, abs(fl.get('balance', 0.0)))
                elif percentage_base in ('total_equity', 'equity'):
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        fid = str(fl.get('id') or '').lower()
                        if ('equity' in fn or 'capital' in fn or 'equity' in fid) and fl.get('level') in (1, 2):
                            bal = abs(fl.get('balance', 0.0))
                            if bal > base_balance:
                                base_balance = bal
                elif percentage_base in ('total_liabilities_equity', 'liabilities_equity'):
                    liab = 0.0
                    eq = 0.0
                    for fl in lines:
                        fn = (fl.get('name') or '').strip().lower()
                        if 'liabilit' in fn and fl.get('level') == 1:
                            liab = max(liab, abs(fl.get('balance', 0.0)))
                        elif ('equity' in fn or 'capital' in fn) and fl.get('level') == 1:
                            eq = max(eq, abs(fl.get('balance', 0.0)))
                    base_balance = liab + eq

            # 3. Match by name keyword or id across lines
            if not base_balance:
                target = base_name.lower().replace('total', '').strip()
                for fl in lines:
                    fn = (fl.get('name') or '').strip().lower()
                    fid = str(fl.get('id') or '').lower()
                    if (target and target in fn) or percentage_base in fid:
                        bal = abs(fl.get('balance', 0.0))
                        if bal:
                            base_balance = bal
                            break

            # 4. If not found in current report lines (e.g. cross-statement base like Revenue on Balance Sheet), query move lines
            if not base_balance:
                account_type_map = {
                    'revenue': ['income', 'income_other'],
                    'costs_of_revenue': ['expense_direct_cost'],
                    'operating_expenses': ['expense', 'expense_depreciation'],
                    'other_income': ['income_other'],
                    'other_expenses': ['expense_other'],
                    'total_assets': ['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments', 'asset_fixed'],
                    'assets': ['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments', 'asset_fixed'],
                    'current_assets': ['asset_receivable', 'asset_cash', 'asset_current', 'asset_prepayments'],
                    'bank_and_cash': ['asset_cash'],
                    'receivables': ['asset_receivable'],
                    'prepayments': ['asset_prepayments'],
                    'fixed_assets': ['asset_fixed'],
                    'non_current_assets': ['asset_non_current', 'asset_fixed'],
                    'total_liabilities': ['liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current'],
                    'liabilities': ['liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current'],
                    'current_liabilities': ['liability_payable', 'liability_credit_card', 'liability_current'],
                    'payables': ['liability_payable'],
                    'non_current_liabilities': ['liability_non_current'],
                    'total_equity': ['equity', 'equity_unaffected'],
                    'equity': ['equity', 'equity_unaffected'],
                    'retained_earnings': ['equity_unaffected'],
                }
                date_from = form_data.get('date_from')
                date_to = form_data.get('date_to')
                target_move = form_data.get('target_move', 'posted')

                domain = [('company_id', 'in', self.env.companies.ids)]
                if target_move == 'posted':
                    domain.append(('move_id.state', '=', 'posted'))
                else:
                    domain.append(('move_id.state', 'in', ('posted', 'draft')))
                if date_from:
                    domain.append(('date', '>=', date_from))
                if date_to:
                    domain.append(('date', '<=', date_to))
                journal_ids = (form_data.get('used_context') or {}).get('journal_ids')
                if journal_ids:
                    domain.append(('journal_id', 'in', journal_ids))

                if percentage_base in ('gross_profit', 'operating_income', 'net_profit'):
                    rev_amls = self.env['account.move.line'].search(domain + [('account_id.account_type', 'in', ['income', 'income_other'])])
                    rev = abs(sum(rev_amls.mapped('balance')))
                    cogs_amls = self.env['account.move.line'].search(domain + [('account_id.account_type', 'in', ['expense_direct_cost'])])
                    cogs = abs(sum(cogs_amls.mapped('balance')))
                    opex_amls = self.env['account.move.line'].search(domain + [('account_id.account_type', 'in', ['expense', 'expense_depreciation'])])
                    opex = abs(sum(opex_amls.mapped('balance')))
                    gp = rev - cogs
                    op_inc = gp - opex
                    if percentage_base == 'gross_profit':
                        base_balance = gp
                    elif percentage_base in ('operating_income', 'net_profit'):
                        base_balance = op_inc
                elif percentage_base in ('total_liabilities_equity', 'liabilities_equity'):
                    l_types = account_type_map['total_liabilities'] + account_type_map['total_equity']
                    amls = self.env['account.move.line'].search(domain + [('account_id.account_type', 'in', l_types)])
                    base_balance = abs(sum(amls.mapped('balance')))
                elif percentage_base in account_type_map:
                    target_types = account_type_map[percentage_base]
                    amls = self.env['account.move.line'].search(domain + [('account_id.account_type', 'in', target_types)])
                    base_balance = abs(sum(amls.mapped('balance')))

            # 5. Fallback if base is genuinely 0.0 in the company
            if not base_balance:
                if is_bs:
                    for fl in lines:
                        if 'asset' in (fl.get('name') or '').lower() and fl.get('balance'):
                            base_balance = abs(fl['balance'])
                            break
                elif is_pl:
                    for fl in lines:
                        if 'revenue' in (fl.get('name') or '').lower() and fl.get('balance'):
                            base_balance = abs(fl['balance'])
                            break
                if not base_balance:
                    for fl in lines:
                        if fl.get('level') == 1 and fl.get('balance'):
                            bal = abs(fl['balance'])
                            if bal > base_balance:
                                base_balance = bal

            columns.append({
                'label': f'% of {base_name}',
                'field': 'percentage_val',
                'type': 'percentage'
            })

            for fl in lines:
                bal = fl.get('balance')
                if bal is None:
                    bal = fl.get('net', fl.get('total', 0.0))
                if bal is None:
                    bal = 0.0
                if base_balance and abs(base_balance) > 0.0001:
                    val = (bal / base_balance) * 100.0
                    if abs(val) < 0.005 or val == 0.0:
                        val = 0.0
                    fl['percentage_val'] = f"{val:,.2f} %"
                else:
                    fl['percentage_val'] = "0.00 %"

        elif form_data.get('comparison_in') == 'percentage' and cmp_periods_info:
            for cmp_info in cmp_periods_info:
                p = cmp_info['p']
                field_name = f'balance_cmp_{p}_pct'
                if any(c.get('field') == field_name for c in columns):
                    continue
                columns.append({
                    'label': f"% Change",
                    'field': field_name,
                    'type': 'percentage'
                })
                for fl in lines:
                    cmp_bal = fl.get(f'balance_cmp_{p}', 0.0)
                    curr_bal = fl.get('balance', 0.0)
                    if cmp_bal and abs(cmp_bal) > 0.0001:
                        diff_pct = ((curr_bal - cmp_bal) / abs(cmp_bal)) * 100.0
                        if abs(diff_pct) < 0.005 or diff_pct == 0.0:
                            diff_pct = 0.0
                        fl[field_name] = f"{diff_pct:,.2f} %"
                    else:
                        if curr_bal and abs(curr_bal) > 0.0001:
                            fl[field_name] = "100.00 %"
                        else:
                            fl[field_name] = "0.00 %"

    @api.model
    def get_report_data(self, model_name, wizard_id, data):
        # Several reports read journal items with raw SQL, which bypasses ACLs:
        # restrict the endpoint to users allowed to see accounting figures.
        if not self.env.su and not self.env.user.has_group('account.group_account_readonly'):
            raise AccessError(_("You are not allowed to access accounting reports."))
        error_result = {
            'title': _('Session Expired'),
            'columns': [{'label': 'Message', 'field': 'message'}],
            'lines': [{'id': 'error', 'message': _('Report session expired or parameters missing. Please generate the report again from the menu.')}],
            'currency_id': self.env.company.currency_id.id,
            'company_id': self.env.company.id,
        }
        
        if not model_name:
            return error_result

        form_data = data.get('form', data)
        
        # In case wizard was garbage collected (breadscrumbs), we try to proceed using form_data

        form_data = data.get('form', data)
        
        if wizard_id:
            try:
                wizard = self.env[model_name].browse(wizard_id)
                if wizard.exists():
                    if hasattr(wizard, 'check_report'):
                        full_action = wizard.check_report()
                        if isinstance(full_action, dict) and full_action.get('data'):
                            wiz_form = full_action['data'].get('form', {})
                            for k, v in wiz_form.items():
                                if k not in form_data:
                                    form_data[k] = v
                    else:
                        if not form_data.get('date_from') and hasattr(wizard, 'date_from') and wizard.date_from:
                            form_data['date_from'] = fields.Date.to_string(wizard.date_from)
                        if not form_data.get('date_to') and hasattr(wizard, 'date_to') and wizard.date_to:
                            form_data['date_to'] = fields.Date.to_string(wizard.date_to)
            except Exception:
                pass
        
        # Ensure used_context is built and up-to-date with date_from/date_to!
        if 'used_context' not in form_data:
            form_data['used_context'] = {}
        
        # Overwrite used_context dates with form_data dates to be safe
        if form_data.get('date_from'):
            form_data['used_context']['date_from'] = form_data['date_from']
            form_data['used_context']['strict_range'] = True
        else:
            form_data['used_context']['date_from'] = False
            
        if form_data.get('date_to'):
            form_data['used_context']['date_to'] = form_data['date_to']
        else:
            form_data['used_context']['date_to'] = False

        if form_data.get('target_move'):
            form_data['used_context']['state'] = form_data['target_move']
            
        if form_data.get('partner_ids'):
            form_data['used_context']['partner_ids'] = self.env['res.partner'].browse(form_data['partner_ids'])
        else:
            form_data['used_context']['partner_ids'] = False
            
        analytic_acc_ids = list(form_data.get('analytic_account_ids') or [])
        analytic_plan_ids = list(form_data.get('analytic_plan_ids') or [])
        if analytic_acc_ids or analytic_plan_ids:
            analytic_accounts = self.env['account.analytic.account'].browse(analytic_acc_ids)
            if analytic_plan_ids:
                plan_accounts = self.env['account.analytic.account'].search([('plan_id', 'in', analytic_plan_ids)])
                analytic_accounts |= plan_accounts
            form_data['used_context']['analytic_account_ids'] = analytic_accounts if analytic_accounts else False
            all_analytic_ids = analytic_accounts.ids
            form_data['analytic_account_ids'] = all_analytic_ids
            if 'form' in data:
                data['form']['analytic_account_ids'] = all_analytic_ids
                data['form']['analytic_plan_ids'] = analytic_plan_ids
                if 'used_context' in data['form']:
                    data['form']['used_context']['analytic_account_ids'] = analytic_accounts if analytic_accounts else False
        else:
            form_data['used_context']['analytic_account_ids'] = False

        # Comparison logic
        cmp_periods_info = []
        date_from_str = form_data.get('date_from')
        date_to_str = form_data.get('date_to')
        base_label = 'Balance'
        if date_to_str:
            try:
                # Convert YYYY-MM-DD to DD/MM/YYYY for label
                dparts = date_to_str.split('-')
                if len(dparts) == 3:
                    base_label = f"As of {dparts[2]}/{dparts[1]}/{dparts[0]}"
                else:
                    base_label = _('As of %s') % date_to_str
            except Exception:
                base_label = _('As of %s') % date_to_str

        if form_data.get('comparison') and form_data.get('comparison') != 'no_comparison':
            date_from = fields.Date.from_string(date_from_str) if date_from_str else False
            date_to = fields.Date.from_string(date_to_str) if date_to_str else False
            
            if date_from and date_to:
                if form_data['comparison'] == 'previous_period':
                    periods = int(form_data.get('previous_periods', 1))
                    delta = date_to - date_from + timedelta(days=1)
                    for p in range(1, periods + 1):
                        date_from_cmp = date_from - (delta * p)
                        date_to_cmp = date_from - (delta * (p - 1)) - timedelta(days=1)
                        cmp_date_to_str = fields.Date.to_string(date_to_cmp)
                        dparts = cmp_date_to_str.split('-')
                        label = f"As of {dparts[2]}/{dparts[1]}/{dparts[0]}" if len(dparts) == 3 else f"As of {cmp_date_to_str}"
                        cmp_periods_info.append({
                            'p': p,
                            'date_from': fields.Date.to_string(date_from_cmp),
                            'date_to': cmp_date_to_str,
                            'label': label
                        })
                elif form_data['comparison'] == 'same_last_year':
                    periods = int(form_data.get('previous_periods', 1))
                    for p in range(1, periods + 1):
                        date_from_cmp = date_from - relativedelta(years=p)
                        date_to_cmp = date_to - relativedelta(years=p)
                        cmp_date_to_str = fields.Date.to_string(date_to_cmp)
                        dparts = cmp_date_to_str.split('-')
                        label = f"As of {dparts[2]}/{dparts[1]}/{dparts[0]}" if len(dparts) == 3 else f"As of {cmp_date_to_str}"
                        cmp_periods_info.append({
                            'p': p,
                            'date_from': fields.Date.to_string(date_from_cmp),
                            'date_to': cmp_date_to_str,
                            'label': label
                        })
                elif form_data['comparison'] in ('specific_date', 'custom_dates'):
                    date_to_cmp_str = form_data.get('date_to_cmp')
                    date_from_cmp_str = form_data.get('date_from_cmp') or date_to_cmp_str
                    if date_to_cmp_str:
                        if date_from_cmp_str and date_from_cmp_str != date_to_cmp_str:
                            f_parts = date_from_cmp_str.split('-')
                            t_parts = date_to_cmp_str.split('-')
                            if len(f_parts) == 3 and len(t_parts) == 3:
                                label = f"{f_parts[2]}/{f_parts[1]}/{f_parts[0]} - {t_parts[2]}/{t_parts[1]}/{t_parts[0]}"
                            else:
                                label = f"{date_from_cmp_str} - {date_to_cmp_str}"
                        else:
                            dparts = date_to_cmp_str.split('-')
                            label = f"As of {dparts[2]}/{dparts[1]}/{dparts[0]}" if len(dparts) == 3 else f"As of {date_to_cmp_str}"
                        cmp_periods_info.append({
                            'p': 1,
                            'date_from': date_from_cmp_str,
                            'date_to': date_to_cmp_str,
                            'label': label
                        })

        # Put it back in data just in case
        data['form'] = form_data

        # --- MULTI LEDGER / JOURNAL GROUP LOGIC ---
        available_ledgers = []
        ledger_journals_map = {}
        seen_names = set()

        # 1. Custom account.multi.ledger (configured by user under Configuration > Multi Ledgers)
        if 'account.multi.ledger' in self.env:
            try:
                company_id = self.env.company.id
                domain = ['|', ('company_id', '=', False), ('company_id', '=', company_id)]
                for ledger in self.env['account.multi.ledger'].sudo().search(domain):
                    l_id = ledger.id
                    l_name = ledger.name or f"Ledger {l_id}"
                    available_ledgers.append({'id': l_id, 'name': l_name})
                    seen_names.add(l_name.strip().lower())
                    j_ids = ledger.journal_ids.ids
                    ledger_journals_map[l_id] = j_ids
                    ledger_journals_map[str(l_id)] = j_ids
            except Exception as e:
                _logger.warning("Error loading account.multi.ledger: %s", e)

        # 2. Standard Odoo Journal Groups (account.journal.group)
        if 'account.journal.group' in self.env:
            try:
                for group in self.env['account.journal.group'].sudo().search([('included_journal_ids.company_id', 'in', self.env.companies.ids)]):
                    g_id = group.id
                    g_name = group.name
                    if isinstance(g_name, dict):
                        g_name = g_name.get(self.env.lang or 'en_US') or list(g_name.values())[0] if g_name else 'Unnamed'
                    g_name = str(g_name or f"Group {g_id}").strip()

                    if hasattr(group, 'included_journal_ids') and group.included_journal_ids:
                        included_ids = group.included_journal_ids.ids
                    elif hasattr(group, 'excluded_journal_ids'):
                        comp_id = getattr(group, 'company_id', None) and group.company_id.id or self.env.company.id
                        company_journals = self.env['account.journal'].sudo().search([('company_id', '=', comp_id)])
                        included_ids = (company_journals - group.excluded_journal_ids).ids
                    else:
                        included_ids = []

                    # Journal groups always use a prefixed key so they can never
                    # overwrite an account.multi.ledger entry sharing the same id.
                    if g_name.lower() not in seen_names:
                        key = f"jg_{g_id}"
                        available_ledgers.append({'id': key, 'name': g_name})
                        seen_names.add(g_name.lower())
                        ledger_journals_map[key] = included_ids
            except Exception as e:
                _logger.warning("Error loading account.journal.group: %s", e)

        # Journals of the selected ledgers, or None when no ledger filter is active.
        # Reports running their own queries must restrict on this explicitly.
        ledger_journal_ids = None
        gaap_options = form_data.get('gaap_options') or {}
        selected_ledger_keys = [k for k, v in gaap_options.items() if v and k != 'local_gaap']
        if selected_ledger_keys and not gaap_options.get('local_gaap'):
            filtered_journal_ids = set()
            for key in selected_ledger_keys:
                if key in ledger_journals_map:
                    filtered_journal_ids.update(ledger_journals_map[key])
                elif str(key).isdigit() and int(key) in ledger_journals_map:
                    filtered_journal_ids.update(ledger_journals_map[int(key)])
            
            selected_journals_list = list(filtered_journal_ids) if filtered_journal_ids else [-1]
            ledger_journal_ids = selected_journals_list
            if 'used_context' not in form_data:
                form_data['used_context'] = {}
            form_data['used_context']['journal_ids'] = selected_journals_list
            form_data['journal_ids'] = selected_journals_list
            if 'form' in data and isinstance(data['form'], dict):
                data['form']['journal_ids'] = selected_journals_list
                if 'used_context' not in data['form']:
                    data['form']['used_context'] = {}
                data['form']['used_context']['journal_ids'] = selected_journals_list
        # ------------------------------------------

        result = {
            'title': 'Report',
            'columns': [],
            'lines': [],
            'currency_id': self.env.company.currency_id.id,
            'currency_symbol': self.env.company.currency_id.symbol or self.env.company.currency_id.name or 'AED',
            'company_id': self.env.company.id,
            'available_ledgers': available_ledgers,
        }

        if model_name == 'accounting.report':
            # Profit and Loss / Balance Sheet
            report_name = form_data.get('account_report_id')
            
            if not form_data.get('account_report_id'):
                raise UserError(_("Report parameters lost or session expired. Please re-generate the report from the menu."))
                
            if isinstance(report_name, list) and len(report_name) > 1:
                result['title'] = report_name[1]
            elif isinstance(report_name, tuple) and len(report_name) > 1:
                result['title'] = report_name[1]
            else:
                result['title'] = _("Financial Report")

            if result['title'] == 'Net Profit' or ('profit' in result['title'].lower() and 'loss' not in result['title'].lower()):
                result['title'] = _("Profit and Loss")
                
            debit_credit = form_data.get('debit_credit')
            
            result['columns'] = [{'label': 'Name', 'field': 'name'}]
            if debit_credit:
                result['columns'].append({'label': 'Debit', 'field': 'debit', 'type': 'monetary'})
                result['columns'].append({'label': 'Credit', 'field': 'credit', 'type': 'monetary'})
            result['columns'].append({'label': base_label, 'field': 'balance', 'type': 'monetary'})
            
            report_model = self.env['report.accounting_pdf_reports.report_financial']
            all_lines_map = {}
            ordered_keys = []
            
            if not cmp_periods_info:
                form_data['enable_filter'] = False
                lines = report_model.with_context(active_model=model_name).get_account_lines(form_data)
                for line in lines:
                    if line.get('level') == 0 or line.get('name') == result.get('title'):
                        continue
                    if line.get('type') == 'account' and not line.get('account_id'):
                        acc_code = (line.get('account_code') or line.get('name', '').split(' ')[0]).strip()
                        account = self.env['account.account'].search([
                            ('code', '=', acc_code),
                            ('company_ids', 'in', self.env.companies.ids)
                        ], limit=1)
                        if account:
                            line['account_id'] = account.id
                            line['account_code'] = account.code
                    key = (line.get('account_id') if line.get('type') == 'account' and line.get('account_id') else line.get('name'), line.get('type'), line.get('level'))
                    if key not in all_lines_map:
                        all_lines_map[key] = line.copy()
                        ordered_keys.append(key)
            else:
                for cmp_info in cmp_periods_info:
                    p = cmp_info['p']
                    result['columns'].append({'label': cmp_info['label'], 'field': f'balance_cmp_{p}', 'type': 'monetary'})
                    
                    form_data['enable_filter'] = True
                    form_data['filter_cmp'] = 'filter_date'
                    form_data['comparison_context'] = dict(form_data['used_context'])
                    form_data['comparison_context']['date_from'] = cmp_info['date_from']
                    form_data['comparison_context']['date_to'] = cmp_info['date_to']
                    
                    lines = report_model.with_context(active_model=model_name).get_account_lines(form_data)
                    for line in lines:
                        if line.get('level') == 0 or line.get('name') == result.get('title'):
                            continue
                        if line.get('type') == 'account' and not line.get('account_id'):
                            acc_code = (line.get('account_code') or line.get('name', '').split(' ')[0]).strip()
                            account = self.env['account.account'].search([
                                ('code', '=', acc_code),
                                ('company_ids', 'in', self.env.companies.ids)
                            ], limit=1)
                            if account:
                                line['account_id'] = account.id
                                line['account_code'] = account.code
                        key = (line.get('account_id') if line.get('type') == 'account' and line.get('account_id') else line.get('name'), line.get('type'), line.get('level'))
                        if key not in all_lines_map:
                            all_lines_map[key] = line.copy()
                            for i in range(1, len(cmp_periods_info) + 1):
                                all_lines_map[key][f'balance_cmp_{i}'] = 0.0
                            ordered_keys.append(key)
                        all_lines_map[key]['balance'] = line['balance']
                        if debit_credit:
                            all_lines_map[key]['debit'] = line.get('debit', 0.0)
                            all_lines_map[key]['credit'] = line.get('credit', 0.0)
                        all_lines_map[key][f'balance_cmp_{p}'] = line.get('balance_cmp', 0.0)

            result['companies_description'] = ", ".join(self.env.companies.mapped('name'))
            is_bs = ('balance sheet' in result['title'].lower())
            is_pl = ('profit' in result['title'].lower() or 'loss' in result['title'].lower())

            if is_pl:
                # Structure Profit and Loss to match standard Odoo Online format:
                # 1. Revenue
                # 2. Costs of Revenue
                # 3. Gross Profit (summary banner)
                # 4. Operating Expenses (with Total Operating Expenses)
                # 5. Operating Income (or Loss) (summary banner)
                # 6. Other Income
                # 7. Other Expenses
                # 8. Net Profit (summary banner)
                # 9. Allocations and Withdrawals

                sections = {
                    'revenue': {'name': _('Revenue'), 'header': None, 'accounts': []},
                    'costs_of_revenue': {'name': _('Costs of Revenue'), 'header': None, 'accounts': []},
                    'operating_expenses': {'name': _('Operating Expenses'), 'header': None, 'accounts': []},
                    'other_income': {'name': _('Other Income'), 'header': None, 'accounts': []},
                    'other_expenses': {'name': _('Other Expenses'), 'header': None, 'accounts': []},
                    'allocations': {'name': _('Allocations and Withdrawals'), 'header': None, 'accounts': []},
                }

                current_section = None
                for key in ordered_keys:
                    raw_line = all_lines_map[key]
                    l_type = raw_line.get('type')
                    l_name = (raw_line.get('name') or '').strip()
                    l_acc_type = raw_line.get('account_type', '')

                    if l_type == 'report':
                        name_lower = l_name.lower()
                        if 'revenue' in name_lower or (name_lower == 'income' and not sections['revenue']['header']):
                            current_section = 'revenue'
                            sections['revenue']['header'] = raw_line.copy()
                            sections['revenue']['header']['name'] = _('Revenue')
                        elif 'cost' in name_lower or 'cogs' in name_lower:
                            current_section = 'costs_of_revenue'
                            sections['costs_of_revenue']['header'] = raw_line.copy()
                            sections['costs_of_revenue']['header']['name'] = _('Costs of Revenue')
                        elif 'operating expense' in name_lower or (name_lower == 'expense' and not sections['operating_expenses']['header']):
                            current_section = 'operating_expenses'
                            sections['operating_expenses']['header'] = raw_line.copy()
                            sections['operating_expenses']['header']['name'] = _('Operating Expenses')
                        elif 'other income' in name_lower:
                            current_section = 'other_income'
                            sections['other_income']['header'] = raw_line.copy()
                            sections['other_income']['header']['name'] = _('Other Income')
                        elif 'other expense' in name_lower:
                            current_section = 'other_expenses'
                            sections['other_expenses']['header'] = raw_line.copy()
                            sections['other_expenses']['header']['name'] = _('Other Expenses')
                        elif 'allocation' in name_lower or 'withdrawal' in name_lower:
                            current_section = 'allocations'
                            sections['allocations']['header'] = raw_line.copy()
                            sections['allocations']['header']['name'] = _('Allocations and Withdrawals')
                    elif l_type == 'account':
                        if l_acc_type in ('expense_direct_cost',):
                            sections['costs_of_revenue']['accounts'].append(raw_line.copy())
                        elif l_acc_type in ('income_other',):
                            sections['other_income']['accounts'].append(raw_line.copy())
                        elif l_acc_type in ('expense_other',):
                            sections['other_expenses']['accounts'].append(raw_line.copy())
                        elif l_acc_type in ('income', 'revenue'):
                            sections['revenue']['accounts'].append(raw_line.copy())
                        elif l_acc_type in ('expense', 'expense_depreciation'):
                            sections['operating_expenses']['accounts'].append(raw_line.copy())
                        else:
                            target = current_section or 'operating_expenses'
                            sections[target]['accounts'].append(raw_line.copy())

                def make_blank_line(line_id, name, level=1, is_banner=False, is_summary=False):
                    bl = {
                        'id': line_id,
                        'name': name,
                        'balance': 0.0,
                        'debit': 0.0,
                        'credit': 0.0,
                        'level': level,
                        'type': 'summary' if (is_banner or is_summary) else 'report',
                        'is_summary_total': is_summary or is_banner,
                        'is_summary_banner': is_banner,
                        'account_ids': [],
                    }
                    for cmp_info in cmp_periods_info:
                        bl[f"balance_cmp_{cmp_info['p']}"] = 0.0
                    return bl

                def get_sec_account_ids(sec_keys):
                    if isinstance(sec_keys, str):
                        sec_keys = [sec_keys]
                    ids = []
                    for k in sec_keys:
                        for a in sections[k]['accounts']:
                            acc_id = a.get('account_id')
                            if acc_id and acc_id not in ids:
                                ids.append(acc_id)
                    return ids

                def compute_section_totals(sec_key):
                    sec = sections[sec_key]
                    accs = sec['accounts']
                    hdr = sec['header']
                    if accs:
                        bal = sum(a.get('balance', 0.0) for a in accs)
                        deb = sum(a.get('debit', 0.0) for a in accs)
                        crd = sum(a.get('credit', 0.0) for a in accs)
                    elif hdr:
                        bal = hdr.get('balance', 0.0)
                        deb = hdr.get('debit', 0.0)
                        crd = hdr.get('credit', 0.0)
                    else:
                        bal = 0.0
                        deb = 0.0
                        crd = 0.0
                    cmps = {}
                    for cmp_info in cmp_periods_info:
                        p = cmp_info['p']
                        if accs:
                            cmps[p] = sum(a.get(f'balance_cmp_{p}', 0.0) for a in accs)
                        elif hdr:
                            cmps[p] = hdr.get(f'balance_cmp_{p}', 0.0)
                        else:
                            cmps[p] = 0.0
                    return bal, deb, crd, cmps

                rev_bal, rev_deb, rev_crd, rev_cmps = compute_section_totals('revenue')
                cogs_bal, cogs_deb, cogs_crd, cogs_cmps = compute_section_totals('costs_of_revenue')
                opex_bal, opex_deb, opex_crd, opex_cmps = compute_section_totals('operating_expenses')
                oinc_bal, oinc_deb, oinc_crd, oinc_cmps = compute_section_totals('other_income')
                oexp_bal, oexp_deb, oexp_crd, oexp_cmps = compute_section_totals('other_expenses')
                alloc_bal, alloc_deb, alloc_crd, alloc_cmps = compute_section_totals('allocations')

                gross_profit_bal = rev_bal - cogs_bal
                operating_income_bal = gross_profit_bal - opex_bal
                net_profit_bal = operating_income_bal + oinc_bal - oexp_bal

                formatted_lines = []

                # 1. Revenue
                rev_hdr = make_blank_line('report_revenue', _('Revenue'), level=1)
                rev_hdr['balance'] = rev_bal
                rev_hdr['debit'] = rev_deb
                rev_hdr['credit'] = rev_crd
                rev_hdr['account_ids'] = get_sec_account_ids('revenue')
                for cmp_info in cmp_periods_info:
                    rev_hdr[f"balance_cmp_{cmp_info['p']}"] = rev_cmps.get(cmp_info['p'], 0.0)
                formatted_lines.append(rev_hdr)
                for a in sections['revenue']['accounts']:
                    a_line = a.copy()
                    a_line['id'] = f"acc_{a.get('account_id') or a.get('name')}"
                    a_line['level'] = 2
                    a_line['account_id'] = a.get('account_id')
                    formatted_lines.append(a_line)

                # 2. Costs of Revenue
                cogs_hdr = make_blank_line('report_costs_of_revenue', _('Costs of Revenue'), level=1)
                cogs_hdr['balance'] = cogs_bal
                cogs_hdr['debit'] = cogs_deb
                cogs_hdr['credit'] = cogs_crd
                cogs_hdr['account_ids'] = get_sec_account_ids('costs_of_revenue')
                for cmp_info in cmp_periods_info:
                    cogs_hdr[f"balance_cmp_{cmp_info['p']}"] = cogs_cmps.get(cmp_info['p'], 0.0)
                formatted_lines.append(cogs_hdr)
                for a in sections['costs_of_revenue']['accounts']:
                    a_line = a.copy()
                    a_line['id'] = f"acc_{a.get('account_id') or a.get('name')}"
                    a_line['level'] = 2
                    a_line['account_id'] = a.get('account_id')
                    formatted_lines.append(a_line)

                # 3. Gross Profit (summary banner)
                gp_line = make_blank_line('summary_gross_profit', _('Gross Profit'), level=1, is_banner=True)
                gp_line['balance'] = gross_profit_bal
                gp_line['account_ids'] = get_sec_account_ids(['revenue', 'costs_of_revenue'])
                for cmp_info in cmp_periods_info:
                    p = cmp_info['p']
                    gp_line[f'balance_cmp_{p}'] = rev_cmps.get(p, 0.0) - cogs_cmps.get(p, 0.0)
                formatted_lines.append(gp_line)

                # 4. Operating Expenses
                opex_hdr = make_blank_line('report_operating_expenses', _('Operating Expenses'), level=1)
                opex_hdr['balance'] = opex_bal
                opex_hdr['debit'] = opex_deb
                opex_hdr['credit'] = opex_crd
                opex_hdr['account_ids'] = get_sec_account_ids('operating_expenses')
                for cmp_info in cmp_periods_info:
                    opex_hdr[f"balance_cmp_{cmp_info['p']}"] = opex_cmps.get(cmp_info['p'], 0.0)
                formatted_lines.append(opex_hdr)
                for a in sections['operating_expenses']['accounts']:
                    a_line = a.copy()
                    a_line['id'] = f"acc_{a.get('account_id') or a.get('name')}"
                    a_line['level'] = 2
                    a_line['account_id'] = a.get('account_id')
                    formatted_lines.append(a_line)
                if sections['operating_expenses']['accounts']:
                    tot_opex = make_blank_line('summary_total_operating_expenses', _('Total Operating Expenses'), level=2, is_summary=True)
                    tot_opex['balance'] = opex_bal
                    tot_opex['debit'] = opex_deb
                    tot_opex['credit'] = opex_crd
                    tot_opex['account_ids'] = get_sec_account_ids('operating_expenses')
                    for cmp_info in cmp_periods_info:
                        tot_opex[f"balance_cmp_{cmp_info['p']}"] = opex_cmps.get(cmp_info['p'], 0.0)
                    formatted_lines.append(tot_opex)

                # 5. Operating Income (or Loss) (summary banner)
                oi_line = make_blank_line('summary_operating_income', _('Operating Income (or Loss)'), level=1, is_banner=True)
                oi_line['balance'] = operating_income_bal
                oi_line['account_ids'] = get_sec_account_ids(['revenue', 'costs_of_revenue', 'operating_expenses'])
                for cmp_info in cmp_periods_info:
                    p = cmp_info['p']
                    oi_line[f'balance_cmp_{p}'] = (rev_cmps.get(p, 0.0) - cogs_cmps.get(p, 0.0)) - opex_cmps.get(p, 0.0)
                formatted_lines.append(oi_line)

                # 6. Other Income
                oinc_hdr = make_blank_line('report_other_income', _('Other Income'), level=1)
                oinc_hdr['balance'] = oinc_bal
                oinc_hdr['account_ids'] = get_sec_account_ids('other_income')
                for cmp_info in cmp_periods_info:
                    oinc_hdr[f"balance_cmp_{cmp_info['p']}"] = oinc_cmps.get(cmp_info['p'], 0.0)
                formatted_lines.append(oinc_hdr)
                for a in sections['other_income']['accounts']:
                    a_line = a.copy()
                    a_line['id'] = f"acc_{a.get('account_id') or a.get('name')}"
                    a_line['level'] = 2
                    a_line['account_id'] = a.get('account_id')
                    formatted_lines.append(a_line)

                # 7. Other Expenses
                oexp_hdr = make_blank_line('report_other_expenses', _('Other Expenses'), level=1)
                oexp_hdr['balance'] = oexp_bal
                oexp_hdr['account_ids'] = get_sec_account_ids('other_expenses')
                for cmp_info in cmp_periods_info:
                    oexp_hdr[f"balance_cmp_{cmp_info['p']}"] = oexp_cmps.get(cmp_info['p'], 0.0)
                formatted_lines.append(oexp_hdr)
                for a in sections['other_expenses']['accounts']:
                    a_line = a.copy()
                    a_line['id'] = f"acc_{a.get('account_id') or a.get('name')}"
                    a_line['level'] = 2
                    a_line['account_id'] = a.get('account_id')
                    formatted_lines.append(a_line)

                # 8. Net Profit (summary banner)
                np_line = make_blank_line('summary_net_profit', _('Net Profit'), level=1, is_banner=True)
                np_line['balance'] = net_profit_bal
                np_line['account_ids'] = get_sec_account_ids(['revenue', 'costs_of_revenue', 'operating_expenses', 'other_income', 'other_expenses'])
                for cmp_info in cmp_periods_info:
                    p = cmp_info['p']
                    np_line[f'balance_cmp_{p}'] = ((rev_cmps.get(p, 0.0) - cogs_cmps.get(p, 0.0)) - opex_cmps.get(p, 0.0)) + oinc_cmps.get(p, 0.0) - oexp_cmps.get(p, 0.0)
                formatted_lines.append(np_line)

                # 9. Allocations and Withdrawals
                alloc_hdr = make_blank_line('report_allocations', _('Allocations and Withdrawals'), level=1)
                alloc_hdr['balance'] = alloc_bal
                alloc_hdr['account_ids'] = get_sec_account_ids('allocations')
                for cmp_info in cmp_periods_info:
                    alloc_hdr[f"balance_cmp_{cmp_info['p']}"] = alloc_cmps.get(cmp_info['p'], 0.0)
                formatted_lines.append(alloc_hdr)
                for a in sections['allocations']['accounts']:
                    a_line = a.copy()
                    a_line['id'] = f"acc_{a.get('account_id') or a.get('name')}"
                    a_line['level'] = 2
                    a_line['account_id'] = a.get('account_id')
                    formatted_lines.append(a_line)

                result['lines'] = formatted_lines
            else:
                seen_ids = {}
                formatted_lines = []
                for key in ordered_keys:
                    line = all_lines_map[key]
                    base_id = f"{line.get('type')}_{line.get('name')}"
                    if base_id in seen_ids:
                        seen_ids[base_id] += 1
                        line_id = f"{base_id}_{seen_ids[base_id]}"
                    else:
                        seen_ids[base_id] = 0
                        line_id = base_id

                    account_id = line.get('account_id')
                    if not account_id and line.get('type') == 'account':
                        acc_code = (line.get('account_code') or line.get('name', '').split(' ')[0]).strip()
                        account = self.env['account.account'].search([
                            ('code', '=', acc_code),
                            ('company_ids', 'in', self.env.companies.ids)
                        ], limit=1)
                        if account:
                            account_id = account.id

                    formatted_line = {
                        'id': line_id,
                        'name': line.get('name', ''),
                        'debit': line.get('debit', 0.0),
                        'credit': line.get('credit', 0.0),
                        'balance': line.get('balance', 0.0),
                        'level': line.get('level', 1),
                        'type': line.get('type', 'report'),
                        'is_summary_total': line.get('is_summary_total', False),
                        'is_summary_banner': line.get('is_summary_banner', False),
                        'account_id': account_id,
                        'account_ids': line.get('account_ids', []),
                    }
                    for cmp_info in cmp_periods_info:
                        p = cmp_info['p']
                        formatted_line[f'balance_cmp_{p}'] = line.get(f'balance_cmp_{p}', 0.0)
                    formatted_lines.append(formatted_line)
                    
                result['lines'] = formatted_lines

            pl_base_map = None
            if is_pl:
                pl_base_map = {
                    'revenue': rev_bal,
                    'costs_of_revenue': cogs_bal,
                    'gross_profit': gross_profit_bal,
                    'operating_expenses': opex_bal,
                    'operating_income': operating_income_bal,
                    'other_income': oinc_bal,
                    'other_expenses': oexp_bal,
                    'net_profit': net_profit_bal,
                    'allocations': alloc_bal,
                }

            self._compute_percentage_comparison(
                result, form_data, is_pl=is_pl, is_bs=is_bs,
                pl_base_map=pl_base_map,
                cmp_periods_info=cmp_periods_info
            )

            if form_data.get('period_order') == 'ascending' and cmp_periods_info:
                name_cols = [c for c in result['columns'] if c['field'] in ('name', 'debit', 'credit')]
                cmp_cols = [c for c in result['columns'] if c['field'].startswith('balance_cmp_')]
                cmp_cols.reverse()
                bal_col = [c for c in result['columns'] if c['field'] == 'balance']
                other_cols = [c for c in result['columns'] if c not in name_cols and c not in cmp_cols and c not in bal_col]
                result['columns'] = name_cols + cmp_cols + bal_col + other_cols

        elif model_name == 'account.tax.report.wizard':
            result['title'] = _("Tax Report")
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': 'Net', 'field': 'net', 'type': 'monetary'},
                {'label': 'Tax', 'field': 'tax', 'type': 'monetary'},
            ]
            report_model = self.env['report.accounting_pdf_reports.report_tax']
            groups = report_model.with_context(active_model=model_name).get_lines(form_data)
            
            formatted_lines = []
            for group_name, group_lines in groups.items():
                if group_lines:
                    group_tax_total = sum(line.get('tax', 0.0) for line in group_lines)
                    formatted_lines.append({
                        'id': f'group_{group_name}',
                        'name': group_name.capitalize(),
                        'level': 1,
                        'type': 'group',
                        'tax': group_tax_total,
                    })
                    for idx, line in enumerate(group_lines):
                        formatted_lines.append({
                            'id': f'tax_{group_name}_{idx}',
                            'name': line.get('name', ''),
                            'net': line.get('net', 0.0),
                            'tax': line.get('tax', 0.0),
                            'level': 2,
                            'type': 'tax',
                        })
            result['lines'] = formatted_lines
        elif model_name == 'account.tax.extended.wizard':
            result['title'] = _("Tax Report")
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': 'Net', 'field': 'net', 'type': 'monetary'},
                {'label': 'Tax', 'field': 'tax', 'type': 'monetary'},
            ]
            wiz = self.env[model_name].browse(wizard_id)
            if not wiz.exists():
                wiz_vals = form_data.copy()
                wiz_vals.pop('used_context', None)
                wiz_vals.pop('id', None)
                wiz_vals.pop('gaap_options', None)
                wiz = self.env[model_name].create(wiz_vals)

            tax_data = wiz.with_context(report_journal_ids=ledger_journal_ids)._compute_tax_data()
            
            formatted_lines = []
            
            def add_groups(groups_list, section_name):
                if not groups_list:
                    return
                formatted_lines.append({
                    'id': f'section_{section_name}',
                    'name': section_name,
                    'level': 1,
                    'type': 'group',
                    'tax': sum(g['total_tax'] for g in groups_list),
                })
                for group in groups_list:
                    for idx, tax_line in enumerate(group['taxes']):
                        formatted_lines.append({
                            'id': f"tax_{section_name}_{group['group_name']}_{idx}",
                            'name': tax_line['name'],
                            'net': tax_line['base_amount'],
                            'tax': tax_line['tax_amount'],
                            'tax_id': tax_line['tax_id'],
                            'level': 2,
                            'type': 'tax',
                        })
                        
            add_groups(tax_data['sale_groups'], 'Sales')
            add_groups(tax_data['purchase_groups'], 'Purchases')
            result['lines'] = formatted_lines
        elif model_name == 'account.executive.summary.wizard':
            result['title'] = _("Executive Summary")
            result['columns'] = [
                {'label': '', 'field': 'name'},
            ]
            
            wiz = self.env[model_name].browse(wizard_id)
            if not wiz.exists():
                wiz_vals = form_data.copy()
                wiz_vals.pop('used_context', None)
                wiz_vals.pop('id', None)
                wiz_vals.pop('gaap_options', None)
                wiz = self.env[model_name].create(wiz_vals)
            
            data = wiz.with_context(report_journal_ids=ledger_journal_ids)._compute_summary_data()
            current = data['current']
            comparison = data['comparison']
            
            result['columns'].append({'label': 'Balance', 'field': 'balance', 'type': 'monetary'})
            if comparison:
                result['columns'].append({'label': 'Comparison', 'field': 'balance_cmp', 'type': 'monetary'})

            formatted_lines = []
            def add_line(name, val, cmp_val=None, type='monetary', level=2):
                formatted_lines.append({
                    'id': str(uuid.uuid4()),
                    'name': name,
                    'level': level,
                    'balance': val,
                    'balance_cmp': cmp_val if cmp_val is not None else 0.0,
                    'type': type,
                })

            def add_header(name):
                formatted_lines.append({
                    'id': str(uuid.uuid4()),
                    'name': name,
                    'level': 1,
                    'type': 'group',
                })

            add_header('Cash')
            add_line('Cash received', current['cash_received'], comparison['cash_received'] if comparison else None)
            add_line('Cash spent', -current['cash_spent'], -comparison['cash_spent'] if comparison else None)
            add_line('Cash surplus', current['cash_surplus'], comparison['cash_surplus'] if comparison else None)
            add_line('Closing bank balance', current['cash'], comparison['cash'] if comparison else None)

            add_header('Profitability')
            add_line('Revenue', current['revenue'], comparison['revenue'] if comparison else None)
            add_line('Cost of Revenue', current['cogs'], comparison['cogs'] if comparison else None)
            add_line('Gross profit', current['gross_profit'], comparison['gross_profit'] if comparison else None)
            add_line('Expenses', current['opex'], comparison['opex'] if comparison else None)
            add_line('Net Profit', current['net_profit'], comparison['net_profit'] if comparison else None)

            add_header('Balance Sheet')
            add_line('Receivables', current['ar'], comparison['ar'] if comparison else None)
            add_line('Payables', -current['ap'], -comparison['ap'] if comparison else None)
            add_line('Net assets', current['net_assets'], comparison['net_assets'] if comparison else None)

            add_header('Performance')
            add_line('Gross profit margin (gross profit / operating income)', current['gross_margin'], comparison['gross_margin'] if comparison else None, type='percent')
            add_line('Net profit margin (net profit / revenue)', current['net_margin'], comparison['net_margin'] if comparison else None, type='percent')
            add_line('Return on investments (net profit / assets)', current['roi'], comparison['roi'] if comparison else None, type='percent')

            add_header('Position')
            add_line('Average debtors days', current['avg_debtors_days'], comparison['avg_debtors_days'] if comparison else None, type='number')
            add_line('Average creditors days', current['avg_creditors_days'], comparison['avg_creditors_days'] if comparison else None, type='number')
            add_line('Short-term cash forecast', current['short_term_cash_forecast'], comparison['short_term_cash_forecast'] if comparison else None)
            add_line('Current assets to liabilities', current['current_ratio'], comparison['current_ratio'] if comparison else None, type='number')

            result['lines'] = formatted_lines

        elif model_name == 'account.report.partner.ledger':
            result['title'] = _("Partner Ledger")
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': 'JRNL', 'field': 'journal'},
                {'label': 'Account', 'field': 'account'},
                {'label': 'Date', 'field': 'date'},
                {'label': 'Due Date', 'field': 'date_maturity'},
                {'label': 'Matching', 'field': 'matching'},
                {'label': 'Debit', 'field': 'debit', 'type': 'monetary'},
                {'label': 'Credit', 'field': 'credit', 'type': 'monetary'},
                {'label': 'Currency', 'field': 'amount_currency', 'type': 'monetary'},
                {'label': 'Balance', 'field': 'balance', 'type': 'monetary'},
            ]
            
            # Setup account types filter
            selected_account_types = form_data.get('account_types')
            if not selected_account_types:
                account_type_filter = form_data.get('account_type', 'trade')
                if account_type_filter == 'receivable':
                    selected_account_types = ['receivable']
                elif account_type_filter == 'payable':
                    selected_account_types = ['payable']
                elif account_type_filter == 'all':
                    selected_account_types = ['receivable', 'non_trade_receivable', 'payable', 'non_trade_payable']
                else: # 'trade'
                    selected_account_types = ['receivable', 'payable']
            elif isinstance(selected_account_types, str):
                selected_account_types = [selected_account_types]
                
            has_non_trade = 'non_trade' in self.env['account.account']._fields
            acc_id_set = set()
            if 'receivable' in selected_account_types:
                dom = [('account_type', '=', 'asset_receivable')]
                if has_non_trade:
                    dom.append(('non_trade', '=', False))
                acc_id_set.update(self.env['account.account'].search(dom).ids)
            if 'non_trade_receivable' in selected_account_types:
                dom = [('account_type', '=', 'asset_receivable')]
                if has_non_trade:
                    dom.append(('non_trade', '=', True))
                acc_id_set.update(self.env['account.account'].search(dom).ids)
            if 'payable' in selected_account_types:
                dom = [('account_type', '=', 'liability_payable')]
                if has_non_trade:
                    dom.append(('non_trade', '=', False))
                acc_id_set.update(self.env['account.account'].search(dom).ids)
            if 'non_trade_payable' in selected_account_types:
                dom = [('account_type', '=', 'liability_payable')]
                if has_non_trade:
                    dom.append(('non_trade', '=', True))
                acc_id_set.update(self.env['account.account'].search(dom).ids)

            acc_ids = list(acc_id_set) if acc_id_set else [0]

            if 'computed' not in data:
                data['computed'] = {}
            data['computed']['account_ids'] = acc_ids
            data['computed']['move_state'] = ['posted'] if form_data.get('target_move') == 'posted' else ['posted', 'draft']
            
            p_ids = list(form_data.get('partner_ids') or [])
            if form_data.get('partner_category_ids'):
                cat_partners = self.env['res.partner'].search([('category_id', 'in', form_data['partner_category_ids'])]).ids
                p_ids = list(set(p_ids + cat_partners)) or [-1]
            
            form_data['partner_ids'] = p_ids
            if 'form' in data:
                data['form']['partner_ids'] = p_ids
            data['computed']['partner_ids'] = p_ids

            if form_data.get('target_move') != 'posted':
                unposted_count = self.env['account.move'].search_count([('state', '=', 'draft')])
                if unposted_count > 0:
                    result['alert_message'] = _('There are unposted Journal Entries prior or included in this period.')
            
            if 'reconciled' not in form_data:
                form_data['reconciled'] = False
            if 'form' in data and 'reconciled' not in data['form']:
                data['form']['reconciled'] = form_data['reconciled']
                
            report_model = self.env['report.accounting_pdf_reports.report_partnerledger']
            report_data = report_model._get_report_values(None, data)
            data['computed']['account_ids'] = acc_ids
            data['computed']['move_state'] = ['posted'] if form_data.get('target_move') == 'posted' else ['posted', 'draft']
            partners = report_data.get('docs', [])
            
            formatted_lines = []
            total_debit = 0.0
            total_credit = 0.0
            total_balance = 0.0
            
            for p_idx, partner in enumerate(partners):
                p_debit = report_data['sum_partner'](data, partner, 'debit')
                p_credit = report_data['sum_partner'](data, partner, 'credit')
                p_balance = report_data['sum_partner'](data, partner, 'debit - credit')
                
                total_debit += p_debit
                total_credit += p_credit
                total_balance += p_balance
                
                # Level 2: Partner
                formatted_lines.append({
                    'id': f'partner_{partner.id}',
                    'name': partner.name,
                    'debit': p_debit,
                    'credit': p_credit,
                    'balance': p_balance,
                    'level': 2,
                    'type': 'partner',
                    'partner_id': partner.id,
                    'action_buttons': [
                        {'label': 'Partner', 'action': 'open_partner'},
                        {'label': 'Journal Items', 'action': 'open_journal_items'}
                    ]
                })
                
                # Level 3: Lines
                lines = report_data['lines'](data, partner)
                line_ids = [line.get('id') for line in lines if line.get('id')]
                amls = self.env['account.move.line'].browse(line_ids)
                aml_map = {aml.id: aml for aml in amls}
                
                for l_idx, line in enumerate(lines):
                    aml = aml_map.get(line.get('id'))
                    date_maturity = str(aml.date_maturity) if aml and aml.date_maturity else ''
                    matching = aml.full_reconcile_id.name if aml and getattr(aml, 'full_reconcile_id', False) else ''
                    if not matching and aml and (aml.matched_debit_ids or aml.matched_credit_ids):
                        # Simple matching fallback
                        matching = '*'
                        
                    formatted_lines.append({
                        'id': f'partner_{partner.id}_line_{line["id"]}_{l_idx}',
                        'name': line.get('displayed_name') or line.get('name') or line.get('ref') or '',
                        'journal': line.get('code', ''),
                        'account': line.get('a_name', ''),
                        'account_id': aml.account_id.id if aml else False,
                        'move_id': aml.move_id.id if aml else False,
                        'move_type': aml.move_id.move_type if aml else False,
                        'date': str(line.get('date', '')),
                        'date_maturity': date_maturity,
                        'matching': matching,
                        'debit': line.get('debit', 0.0),
                        'credit': line.get('credit', 0.0),
                        'amount_currency': line.get('amount_currency', 0.0),
                        'balance': line.get('progress', 0.0),
                        'level': 3,
                        'type': 'move_line',
                        'partner_id': partner.id,
                        'move_line_id': line.get('id')
                    })
            
            # Prepend Level 1: Partner Ledger Root
            result['lines'] = [{
                'id': 'root',
                'name': 'Partner Ledger',
                'debit': total_debit,
                'credit': total_credit,
                'balance': total_balance,
                'level': 1,
                'type': 'report',
            }] + formatted_lines
            
        elif model_name == 'account.balance.report':
            result['title'] = _("Trial Balance")
            
            # Extract parameters
            date_from = form_data.get('date_from')
            date_to = form_data.get('date_to')
            target_move = form_data.get('target_move', 'posted')
            display_account = form_data.get('display_account', 'all')
            
            period_label = "Current Period"
            if date_from and date_to:
                d_to = datetime.strptime(date_to, "%Y-%m-%d")
                period_label = d_to.strftime("%b %Y") # e.g., "Aug 2026"
            elif date_from:
                period_label = f"Since {date_from}"
            elif date_to:
                period_label = f"Until {date_to}"
                
            result['column_groups'] = [
                {'label': '', 'colspan': 1},
                {'label': 'Initial Balance', 'colspan': 1},
                {'label': period_label, 'colspan': 2},
                {'label': 'End Balance', 'colspan': 1},
            ]
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': 'Balance', 'field': 'initial_balance', 'type': 'monetary'},
                {'label': 'Debit', 'field': 'debit', 'type': 'monetary'},
                {'label': 'Credit', 'field': 'credit', 'type': 'monetary'},
                {'label': 'Balance', 'field': 'end_balance', 'type': 'monetary'},
            ]
            
            accounts = self.env['account.account'].search([], order="code")
            
            domain_initial = []
            domain_period = []
            
            # Cancelled entries never count, even with "All Entries"
            move_states = ['posted'] if target_move == 'posted' else ['posted', 'draft']
            domain_initial.append(('parent_state', 'in', move_states))
            domain_period.append(('parent_state', 'in', move_states))
                
            if date_from:
                domain_initial.append(('date', '<', date_from))
                domain_period.append(('date', '>=', date_from))
                
            if date_to:
                domain_period.append(('date', '<=', date_to))
                
            if form_data.get('journal_ids'):
                domain_initial.append(('journal_id', 'in', form_data['journal_ids']))
                domain_period.append(('journal_id', 'in', form_data['journal_ids']))

            # Filter by analytic accounts in Trial Balance
            resolved_analytic_acc_ids = []
            if form_data.get('used_context', {}).get('analytic_account_ids'):
                ctx_an = form_data['used_context']['analytic_account_ids']
                resolved_analytic_acc_ids = ctx_an.ids if hasattr(ctx_an, 'ids') else (list(ctx_an) if isinstance(ctx_an, (list, tuple, set)) else [ctx_an])
            elif form_data.get('analytic_account_ids'):
                resolved_analytic_acc_ids = list(form_data['analytic_account_ids'])
            if resolved_analytic_acc_ids:
                domain_initial.append(('analytic_distribution', 'in', resolved_analytic_acc_ids))
                domain_period.append(('analytic_distribution', 'in', resolved_analytic_acc_ids))

            # Filter by partners if selected
            if form_data.get('partner_ids'):
                domain_initial.append(('partner_id', 'in', form_data['partner_ids']))
                domain_period.append(('partner_id', 'in', form_data['partner_ids']))
                
            # Compute Initial Balance
            initial_balances = {}
            if date_from:
                from_string, where_string, where_params = self._get_query_components('account.move.line', domain_initial)
                if where_string:
                    self.env.cr.execute(f"SELECT account_id, SUM(debit - credit) as balance FROM {from_string} WHERE {where_string} GROUP BY account_id", where_params)
                    for row in self.env.cr.dictfetchall():
                        initial_balances[row['account_id']] = row['balance']
                        
            # Compute Period Movement
            period_movements = {}
            from_string, where_string, where_params = self._get_query_components('account.move.line', domain_period)
            if where_string:
                self.env.cr.execute(f"SELECT account_id, SUM(debit) as debit, SUM(credit) as credit FROM {from_string} WHERE {where_string} GROUP BY account_id", where_params)
                for row in self.env.cr.dictfetchall():
                    period_movements[row['account_id']] = row
            elif not domain_period:
                self.env.cr.execute(f"SELECT account_id, SUM(debit) as debit, SUM(credit) as credit FROM account_move_line GROUP BY account_id")
                for row in self.env.cr.dictfetchall():
                    period_movements[row['account_id']] = row

            # Group accounts hierarchically
            type_labels = dict(self.env['account.account']._fields['account_type'].selection)
            account_groups_dict = {}
            
            for account in accounts:
                initial_balance = initial_balances.get(account.id, 0.0)
                period_data = period_movements.get(account.id, {'debit': 0.0, 'credit': 0.0})
                debit = period_data['debit'] or 0.0
                credit = period_data['credit'] or 0.0
                end_balance = initial_balance + debit - credit
                
                # Check display criteria
                if display_account == 'not_zero' and round(end_balance, 2) == 0:
                    continue
                if display_account == 'movement' and round(debit, 2) == 0 and round(credit, 2) == 0:
                    continue
                
                # Determine group
                code = str(account.code or '')
                acc_group = getattr(account, 'group_id', False)
                if acc_group:
                    pfx = str(acc_group.code_prefix_start or (code[:2] if len(code) >= 2 else code) or '')
                    grp_code = pfx.ljust(6, '0') if len(pfx) <= 6 else pfx
                    grp_id = f"grp_{acc_group.id}"
                    grp_name = f"{grp_code} {acc_group.name}"
                else:
                    pfx = code[:2] if len(code) >= 2 else code
                    grp_code = pfx.ljust(6, '0') if len(pfx) <= 6 else pfx
                    type_name = type_labels.get(account.account_type, account.account_type.replace('_', ' ').title()) if account.account_type else 'Other'
                    grp_id = f"pfx_{pfx}_{account.account_type}"
                    grp_name = f"{grp_code} {type_name}"
                
                if grp_id not in account_groups_dict:
                    account_groups_dict[grp_id] = {
                        'id': grp_id,
                        'name': grp_name,
                        'initial_balance': 0.0,
                        'debit': 0.0,
                        'credit': 0.0,
                        'end_balance': 0.0,
                        'level': 1,
                        'type': 'group',
                        'accounts': []
                    }
                
                account_groups_dict[grp_id]['initial_balance'] += initial_balance
                account_groups_dict[grp_id]['debit'] += debit
                account_groups_dict[grp_id]['credit'] += credit
                account_groups_dict[grp_id]['end_balance'] += end_balance
                
                account_groups_dict[grp_id]['accounts'].append({
                    'id': f'account_{account.id}',
                    'name': f"{account.code} {account.name}" if account.code else (account.name or ''),
                    'initial_balance': initial_balance,
                    'debit': debit,
                    'credit': credit,
                    'end_balance': end_balance,
                    'level': 2,
                    'type': 'account',
                    'account_id': account.id,
                })
            
            formatted_lines = []
            total_initial = 0.0
            total_debit = 0.0
            total_credit = 0.0
            total_end = 0.0
            
            for grp_id, grp_data in account_groups_dict.items():
                total_initial += grp_data['initial_balance']
                total_debit += grp_data['debit']
                total_credit += grp_data['credit']
                total_end += grp_data['end_balance']
                
                # Add Level 1 Group Header
                formatted_lines.append({
                    'id': grp_data['id'],
                    'name': grp_data['name'],
                    'initial_balance': grp_data['initial_balance'],
                    'debit': grp_data['debit'],
                    'credit': grp_data['credit'],
                    'end_balance': grp_data['end_balance'],
                    'level': 1,
                    'type': 'group',
                })
                
                # Add Level 2 Accounts under this Group
                for acc_line in grp_data['accounts']:
                    formatted_lines.append(acc_line)
                
            unallocated = -total_initial
            if round(unallocated, 2) != 0:
                formatted_lines.append({
                    'id': 'unallocated',
                    'name': _('Result Brought Forward'),
                    'initial_balance': unallocated,
                    'debit': 0.0,
                    'credit': 0.0,
                    'end_balance': unallocated,
                    'level': 2,
                    'type': 'account',
                })
                total_initial += unallocated
                total_end += unallocated
                
            # Add Total Row
            formatted_lines.append({
                'id': 'total',
                'name': _('Total'),
                'initial_balance': total_initial,
                'debit': total_debit,
                'credit': total_credit,
                'end_balance': total_end,
                'level': 1,
                'type': 'total',
                'is_summary_total': True,
            })
            
            if target_move != 'posted':
                unposted_count = self.env['account.move'].search_count([('state', '=', 'draft')])
                if unposted_count > 0:
                    result['alert_message'] = _('There are unposted Journal Entries prior or included in this period.')
                    
            result['lines'] = formatted_lines
            
        elif model_name == 'account.report.general.ledger':
            result['title'] = _("General Ledger")
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': 'Date', 'field': 'date'},
                {'label': 'Partner', 'field': 'partner'},
                {'label': 'Currency', 'field': 'amount_currency', 'type': 'monetary'},
                {'label': 'Debit', 'field': 'debit', 'type': 'monetary'},
                {'label': 'Credit', 'field': 'credit', 'type': 'monetary'},
                {'label': 'Balance', 'field': 'balance', 'type': 'monetary'},
            ]
            
            if form_data.get('target_move') != 'posted':
                unposted_count = self.env['account.move'].search_count([('state', '=', 'draft')])
                if unposted_count > 0:
                    result['alert_message'] = _('There are unposted Journal Entries prior or included in this period.')
            
            report_model = self.env['report.accounting_pdf_reports.report_general_ledger'].with_context(active_model='account.report.general.ledger')
            report_data = report_model._get_report_values(None, data)
            accounts_res = report_data.get('Accounts', [])
            
            # Group accounts in General Ledger
            type_labels = dict(self.env['account.account']._fields['account_type'].selection)
            acc_objs = self.env['account.account'].search([('code', 'in', [a.get('code') for a in accounts_res])])
            acc_by_code = {a.code: a for a in acc_objs}
            
            display_account = form_data.get('display_account', 'movement')
            gl_groups = {}
            for account in accounts_res:
                a_debit = account.get('debit', 0.0)
                a_credit = account.get('credit', 0.0)
                a_balance = account.get('balance', 0.0)
                
                # Skip zero-balance, zero-movement accounts when display_account is movement or not_zero
                if display_account == 'movement' and round(a_debit, 2) == 0 and round(a_credit, 2) == 0 and round(a_balance, 2) == 0:
                    continue
                if display_account == 'not_zero' and round(a_balance, 2) == 0:
                    continue

                code = str(account.get('code') or '')
                acc_obj = acc_by_code.get(code)
                acc_group = getattr(acc_obj, 'group_id', False) if acc_obj else False
                if acc_group:
                    pfx = str(acc_group.code_prefix_start or (code[:2] if len(code) >= 2 else code) or '')
                    grp_code = pfx.ljust(6, '0') if len(pfx) <= 6 else pfx
                    grp_id = f"gl_grp_{acc_group.id}"
                    grp_name = f"{grp_code} {acc_group.name}"
                else:
                    pfx = code[:2] if len(code) >= 2 else code
                    grp_code = pfx.ljust(6, '0') if len(pfx) <= 6 else pfx
                    type_name = type_labels.get(acc_obj.account_type, acc_obj.account_type.replace('_', ' ').title()) if acc_obj and acc_obj.account_type else 'Other'
                    grp_id = f"gl_pfx_{pfx}"
                    grp_name = f"{grp_code} {type_name}"
                    
                if grp_id not in gl_groups:
                    gl_groups[grp_id] = {
                        'id': grp_id,
                        'name': grp_name,
                        'debit': 0.0,
                        'credit': 0.0,
                        'balance': 0.0,
                        'level': 1,
                        'type': 'group',
                        'accounts': []
                    }
                    
                gl_groups[grp_id]['debit'] += a_debit
                gl_groups[grp_id]['credit'] += a_credit
                gl_groups[grp_id]['balance'] += a_balance
                gl_groups[grp_id]['accounts'].append(account)

            formatted_lines = []
            total_debit = 0.0
            total_credit = 0.0
            total_balance = 0.0
            
            for grp_id, grp_data in gl_groups.items():
                total_debit += grp_data['debit']
                total_credit += grp_data['credit']
                total_balance += grp_data['balance']
                
                formatted_lines.append({
                    'id': grp_data['id'],
                    'name': grp_data['name'],
                    'debit': grp_data['debit'],
                    'credit': grp_data['credit'],
                    'balance': grp_data['balance'],
                    'level': 1,
                    'type': 'group',
                    'action_buttons': [{'label': _('Journal Items'), 'action': 'open_journal_items'}]
                })
                
                for account in grp_data['accounts']:
                    a_debit = account.get('debit', 0.0)
                    a_credit = account.get('credit', 0.0)
                    a_balance = account.get('balance', 0.0)
                    acc_obj = acc_by_code.get(account.get('code'))
                    
                    formatted_lines.append({
                        'id': f'account_{account["code"]}',
                        'name': f"{account['code']} {account['name']}" if account.get('code') else (account.get('name') or ''),
                        'debit': a_debit,
                        'credit': a_credit,
                        'balance': a_balance,
                        'level': 2,
                        'type': 'account',
                        'account_id': acc_obj.id if acc_obj else False,
                        'action_buttons': [{'label': _('Journal Items'), 'action': 'open_journal_items'}]
                    })
                    
                    for line in account.get('move_lines', []):
                        # initial balance line has lid = 0
                        is_initial = line.get('lid') == 0
                        name_label = _('Initial Balance') if is_initial else (line.get('lname') or '')
                        if not is_initial and line.get('lref'):
                            name_label = f"{name_label} - {line.get('lref')}"
                        
                        aml_obj = self.env['account.move.line'].browse(line.get('lid')) if not is_initial else False
                        move_id = aml_obj.move_id.id if aml_obj else False
                        move_type = aml_obj.move_id.move_type if aml_obj else 'entry'
                        
                        formatted_lines.append({
                            'id': f'aml_{line.get("lid")}_{account["code"]}',
                            'name': name_label,
                            'date': line.get('ldate') if not is_initial else '',
                            'partner': line.get('partner_name') or '',
                            'amount_currency': line.get('amount_currency') or 0.0,
                            'debit': line.get('debit', 0.0),
                            'credit': line.get('credit', 0.0),
                            'balance': line.get('balance', 0.0),
                            'level': 3,
                            'type': 'move_line',
                            'move_id': move_id,
                            'move_line_id': line.get('lid') if not is_initial else False,
                            'move_type': move_type,
                        })
            
            # Initial Balance Check
            date_from = form_data.get('date_from')
            unallocated = 0.0
            if date_from:
                domain_initial = []
                if form_data.get('target_move') == 'posted':
                    domain_initial.append(('move_id.state', '=', 'posted'))
                else:
                    domain_initial.append(('move_id.state', 'in', ('posted', 'draft')))
                domain_initial.append(('date', '<', date_from))
                if ledger_journal_ids:
                    domain_initial.append(('journal_id', 'in', ledger_journal_ids))

                from_string, where_string, where_params = self._get_query_components('account.move.line', domain_initial)
                if where_string:
                    self.env.cr.execute(f"SELECT SUM(debit - credit) as balance FROM {from_string} WHERE {where_string}", where_params)
                    res = self.env.cr.fetchone()
                    if res and res[0]:
                        # The sum of all accounts initial balance
                        unallocated = -res[0]
            
            if round(unallocated, 2) != 0:
                formatted_lines.append({
                    'id': 'unallocated',
                    'name': _('Result Brought Forward'),
                    'debit': 0.0,
                    'credit': 0.0,
                    'balance': unallocated,
                    'level': 2,
                    'type': 'account',
                })
                total_balance += unallocated
            
            formatted_lines.append({
                'id': 'total',
                'name': _('Total General Ledger'),
                'debit': total_debit,
                'credit': total_credit,
                'balance': total_balance,
                'level': 1,
                'type': 'total',
            })
            
            result['lines'] = formatted_lines
        elif model_name == 'account.cash.flow.wizard':
            result['title'] = _("Cash Flow Statement")
            result['columns'] = [
                {'label': 'Name', 'field': 'name'},
                {'label': 'Balance', 'field': 'balance', 'type': 'monetary'},
            ]
            
            wizard = self.env['account.cash.flow.wizard'].browse(wizard_id).exists()
            if not wizard:
                wiz_vals = {k: v for k, v in form_data.items()
                            if k in ('date_from', 'date_to', 'target_move') and v}
                wizard = self.env['account.cash.flow.wizard'].create(wiz_vals)
            cf_data = wizard.with_context(report_journal_ids=ledger_journal_ids)._compute_cash_flow_data()
            
            formatted_lines = []
            
            def add_section(id_str, name, data_dict):
                formatted_lines.append({
                    'id': id_str,
                    'name': name,
                    'balance': data_dict.get('total', 0.0),
                    'level': 3,
                    'type': 'group',
                })
                for acc in data_dict.get('account_lines', []):
                    acc_id_str = f"{id_str}_{acc['id']}"
                    formatted_lines.append({
                        'id': acc_id_str,
                        'name': acc['name'],
                        'balance': acc['balance'],
                        'level': 4,
                        'type': 'account',
                        'account_id': acc['id'],
                        'action_buttons': [{'label': _('Journal Items'), 'action': 'open_journal_items'}]
                    })
                    for tx in acc.get('transactions', []):
                        formatted_lines.append({
                            'id': f"tx_{id_str}_{tx['id']}",
                            'name': tx['name'],
                            'date': tx['date'],
                            'partner': tx['partner_name'],
                            'balance': tx['balance'],
                            'level': 5,
                            'type': 'move_line',
                            'move_id': tx['move_id'],
                            'move_line_id': tx['id'],
                            'move_type': tx['move_type'],
                        })
            
            # 1. Opening Balance
            formatted_lines.append({
                'id': 'opening',
                'name': _('Cash and cash equivalents, beginning of period'),
                'balance': cf_data['opening_cash'],
                'level': 1,
                'type': 'total',
                'is_summary_total': True,
            })
            
            # 2. Net Increase Header
            formatted_lines.append({
                'id': 'net_increase',
                'name': _('Net increase in cash and cash equivalents'),
                'balance': cf_data['net_increase'],
                'level': 1,
                'type': 'total',
                'is_summary_total': True,
            })
            
            # 2a. Operating Activities
            formatted_lines.append({
                'id': 'operating',
                'name': _('Cash flows from operating activities'),
                'balance': cf_data['operating_total'],
                'level': 2,
                'type': 'group',
            })
            add_section('op_adv_in', _('Advance Payments received from customers'), cf_data['op_adv_in'])
            add_section('op_cash_in', _('Cash received from operating activities'), cf_data['op_cash_in'])
            add_section('op_adv_out', _('Advance payments made to suppliers'), cf_data['op_adv_out'])
            add_section('op_cash_out', _('Cash paid for operating activities'), cf_data['op_cash_out'])
            
            # 2b. Investing Activities
            formatted_lines.append({
                'id': 'investing',
                'name': _('Cash flows from investing & extraordinary activities'),
                'balance': cf_data['investing_total'],
                'level': 2,
                'type': 'group',
            })
            add_section('inv_in', _('Cash in'), cf_data['inv_in'])
            add_section('inv_out', _('Cash out'), cf_data['inv_out'])
            
            # 2c. Financing Activities
            formatted_lines.append({
                'id': 'financing',
                'name': _('Cash flows from financing activities'),
                'balance': cf_data['financing_total'],
                'level': 2,
                'type': 'group',
            })
            add_section('fin_in', _('Cash in'), cf_data['fin_in'])
            add_section('fin_out', _('Cash out'), cf_data['fin_out'])
            
            # 2d. Unclassified Activities
            formatted_lines.append({
                'id': 'unclassified',
                'name': _('Cash flows from unclassified activities'),
                'balance': cf_data['unclassified_total'],
                'level': 2,
                'type': 'group',
            })
            add_section('unclass_in', _('Cash in'), cf_data['unclass_in'])
            add_section('unclass_out', _('Cash out'), cf_data['unclass_out'])
            
            # 3. Closing Balance
            formatted_lines.append({
                'id': 'closing',
                'name': _('Cash and cash equivalents, closing balance'),
                'balance': cf_data['closing_cash'],
                'level': 1,
                'type': 'total',
                'is_summary_total': True,
            })
            
            result['lines'] = formatted_lines
        elif model_name == 'account.aged.report':
            wizard = self.env['account.aged.report'].browse(wizard_id) if wizard_id else self.env['account.aged.report']
            account_type = form_data.get('account_type') or (wizard.account_type if wizard.exists() else 'payable')
            is_payable = 'payable' in str(account_type)
            result['title'] = _("Aged Payable") if is_payable else _("Aged Receivable")
            
            p = int(form_data.get('period_length') or (wizard.period_length if wizard.exists() else 30) or 30)
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': 'Invoice Date', 'field': 'invoice_date'},
                {'label': 'At Date', 'field': 'not_due', 'type': 'monetary'},
                {'label': f'1-{p}', 'field': 'p4', 'type': 'monetary'},
                {'label': f'{p+1}-{2*p}', 'field': 'p3', 'type': 'monetary'},
                {'label': f'{2*p+1}-{3*p}', 'field': 'p2', 'type': 'monetary'},
                {'label': f'{3*p+1}-{4*p}', 'field': 'p1', 'type': 'monetary'},
                {'label': 'Older', 'field': 'p0', 'type': 'monetary'},
                {'label': 'Total', 'field': 'total', 'type': 'monetary'},
            ]
            
            cr = self.env.cr
            as_of_raw = form_data.get('as_of_date') or form_data.get('date_to') or (wizard.as_of_date if wizard.exists() else False) or fields.Date.context_today(self)
            if isinstance(as_of_raw, str):
                as_of = fields.Date.from_string(as_of_raw)
            elif isinstance(as_of_raw, datetime):
                as_of = as_of_raw.date()
            elif isinstance(as_of_raw, date):
                as_of = as_of_raw
            else:
                as_of = fields.Date.context_today(self)
                
            company = (wizard.company_id if wizard.exists() else self.env.company) or self.env.company
            show_draft = form_data.get('target_move') != 'posted' if 'target_move' in form_data else getattr(wizard, 'show_draft', False)
            state_filter = "AND am.state IN ('draft', 'posted')" if show_draft else "AND am.state = 'posted'"
            
            # Check for unposted journal entries
            unposted_count = self.env['account.move'].search_count([
                ('state', '=', 'draft'),
                ('company_id', 'in', self.env.companies.ids),
                ('date', '<=', as_of)
            ])
            if unposted_count > 0:
                result['alert_message'] = _('There are unposted Journal Entries prior or included in this period.')
            
            # Active companies string
            result['companies_description'] = ", ".join(self.env.companies.mapped('name'))
            
            # Account type and non_trade filtering
            if account_type == 'payable':
                acc_types = ['liability_payable']
                non_trade_filter = "AND aa.non_trade = FALSE"
            elif account_type == 'non_trade_payable':
                acc_types = ['liability_payable']
                non_trade_filter = "AND aa.non_trade = TRUE"
            elif account_type == 'non_trade_receivable':
                acc_types = ['asset_receivable']
                non_trade_filter = "AND aa.non_trade = TRUE"
            elif account_type == 'trade':
                acc_types = ['asset_receivable', 'liability_payable']
                non_trade_filter = "AND aa.non_trade = FALSE"
            elif account_type == 'all':
                acc_types = ['asset_receivable', 'liability_payable']
                non_trade_filter = ""
            else: # receivable
                acc_types = ['asset_receivable']
                non_trade_filter = "AND aa.non_trade = FALSE"
                
            # Date basis
            date_basis = form_data.get('date_basis') or getattr(wizard, 'date_basis', 'date_maturity')
            
            # Partners filtering
            partner_ids = form_data.get('partner_ids') or (wizard.partner_ids.ids if wizard.exists() else [])
            partner_clause = ''
            partner_args = []
            if partner_ids:
                partner_clause = "AND l.partner_id IN %s"
                partner_args.append(tuple(int(p) for p in partner_ids))
                    
            tag_ids = form_data.get('partner_category_ids') or (wizard.partner_category_ids.ids if wizard.exists() and hasattr(wizard, 'partner_category_ids') else [])
            tags_clause = ''
            tags_args = []
            if tag_ids:
                tags_clause = """
                    AND EXISTS (
                        SELECT 1 FROM res_partner_res_partner_category_rel rel 
                        WHERE rel.partner_id = l.partner_id AND rel.category_id IN %s
                    )
                """
                tags_args.append(tuple(tag_ids))

            journal_clause = ''
            journal_args = []
            if ledger_journal_ids:
                journal_clause = 'AND l.journal_id IN %s'
                journal_args.append(tuple(ledger_journal_ids))

            # Aging interval boundaries relative to as_of
            p4_start = as_of - timedelta(days=p)
            p4_stop = as_of - timedelta(days=1)
            p3_start = as_of - timedelta(days=2*p)
            p3_stop = as_of - timedelta(days=p+1)
            p2_start = as_of - timedelta(days=3*p)
            p2_stop = as_of - timedelta(days=2*p+1)
            p1_start = as_of - timedelta(days=4*p)
            p1_stop = as_of - timedelta(days=3*p+1)
            p0_stop = as_of - timedelta(days=4*p+1)
                
            # Reconciled after as_of date
            cr.execute(
                '''SELECT DISTINCT debit_move_id, credit_move_id
                   FROM account_partial_reconcile
                   WHERE max_date > %s''',
                (as_of,)
            )
            recon_after = []
            for row in cr.fetchall():
                recon_after += [row[0], row[1]]

            recon_clause = '(l.reconciled IS FALSE)'
            recon_args = []
            if recon_after:
                recon_clause = '(l.reconciled IS FALSE OR l.id IN %s)'
                recon_args = [tuple(recon_after)]

            # Pre-fetch partial reconciliations on or before as_of date
            cr.execute('''
                SELECT debit_move_id, SUM(amount) as amt
                FROM account_partial_reconcile
                WHERE max_date <= %s
                GROUP BY debit_move_id
            ''', (as_of,))
            debit_reconciled = {r['debit_move_id']: r['amt'] for r in cr.dictfetchall()}

            cr.execute('''
                SELECT credit_move_id, SUM(amount) as amt
                FROM account_partial_reconcile
                WHERE max_date <= %s
                GROUP BY credit_move_id
            ''', (as_of,))
            credit_reconciled = {r['credit_move_id']: r['amt'] for r in cr.dictfetchall()}

            query = f'''
                SELECT 
                    l.id as line_id,
                    l.partner_id, 
                    rp.name AS partner_name,
                    am.id as move_id,
                    am.name as move_name,
                    am.move_type,
                    l.account_id,
                    l.date as invoice_date,
                    l.date_maturity,
                    l.balance,
                    aa.account_type as acc_type
                FROM account_move_line l
                JOIN account_account aa ON aa.id = l.account_id
                JOIN account_move am ON am.id = l.move_id
                LEFT JOIN res_partner rp ON rp.id = l.partner_id
                WHERE aa.account_type IN %s
                  {non_trade_filter}
                  AND l.date <= %s
                  AND l.company_id IN %s
                  {state_filter}
                  AND {recon_clause}
                  {partner_clause}
                  {tags_clause}
                  {journal_clause}
                  AND l.display_type NOT IN ('line_section', 'line_note')
                ORDER BY rp.name, l.date, am.name
            '''
            cr.execute(query, [tuple(acc_types), as_of, tuple(self.env.companies.ids)] + recon_args + partner_args + tags_args + journal_args)
            lines = cr.dictfetchall()
            
            show_account = getattr(wizard, 'show_account', False)
            account_codes = {}
            if show_account:
                account_ids = list(set([line['account_id'] for line in lines if line['account_id']]))
                accounts = self.env['account.account'].browse(account_ids)
                account_codes = {acc.id: acc.code for acc in accounts}
            
            partners_data = {}
            for line in lines:
                bal = line['balance']
                line_sign = -1 if line['acc_type'] == 'liability_payable' else 1
                
                # Calculate residual balance as of as_of
                if bal > 0:
                    recon = debit_reconciled.get(line['line_id'], 0.0)
                    amt = (bal - recon) * line_sign
                else:
                    recon = credit_reconciled.get(line['line_id'], 0.0)
                    amt = (bal + recon) * line_sign
                
                if round(amt, 2) == 0:
                    continue
                    
                pid = line['partner_id'] or 0
                pname = line['partner_name'] or _('Unknown Partner')
                if pid not in partners_data:
                    partners_data[pid] = {
                        'name': pname,
                        'partner_id': pid,
                        'not_due': 0.0, 'p4': 0.0, 'p3': 0.0, 'p2': 0.0, 'p1': 0.0, 'p0': 0.0, 'total': 0.0,
                        'lines': []
                    }
                    
                mat_date = line['date_maturity'] or line['invoice_date']
                if date_basis == 'date':
                    mat_date = line['invoice_date']
                
                acc_code = account_codes.get(line['account_id'])
                line_name = f"{acc_code} - {line['move_name']}" if show_account and acc_code else line['move_name']
                
                line_data = {
                    'id': f"line_{line['line_id']}",
                    'name': line_name,
                    'invoice_date': str(line['invoice_date']) if line['invoice_date'] else '',
                    'not_due': 0.0, 'p4': 0.0, 'p3': 0.0, 'p2': 0.0, 'p1': 0.0, 'p0': 0.0, 'total': amt,
                    'level': 3,
                    'type': 'account',
                    'move_id': line['move_id'],
                    'move_type': line.get('move_type', 'entry'),
                }
                
                if mat_date >= as_of:
                    line_data['not_due'] = amt
                elif p4_start <= mat_date <= p4_stop:
                    line_data['p4'] = amt
                elif p3_start <= mat_date <= p3_stop:
                    line_data['p3'] = amt
                elif p2_start <= mat_date <= p2_stop:
                    line_data['p2'] = amt
                elif p1_start <= mat_date <= p1_stop:
                    line_data['p1'] = amt
                else:
                    line_data['p0'] = amt
                    
                partners_data[pid]['not_due'] += line_data['not_due']
                partners_data[pid]['p4'] += line_data['p4']
                partners_data[pid]['p3'] += line_data['p3']
                partners_data[pid]['p2'] += line_data['p2']
                partners_data[pid]['p1'] += line_data['p1']
                partners_data[pid]['p0'] += line_data['p0']
                partners_data[pid]['total'] += amt
                partners_data[pid]['lines'].append(line_data)
                
            formatted_lines = []
            g_not_due = g_p4 = g_p3 = g_p2 = g_p1 = g_p0 = g_total = 0.0
            
            hide_lines_at_0 = form_data.get('hide_lines_at_0', True)
            sorted_pids = sorted(partners_data.keys(), key=lambda x: (partners_data[x]['name'] or '').lower())
            
            for pid in sorted_pids:
                pdata = partners_data[pid]
                if hide_lines_at_0 and round(pdata['total'], 2) == 0:
                    continue
                g_not_due += pdata['not_due']
                g_p4 += pdata['p4']
                g_p3 += pdata['p3']
                g_p2 += pdata['p2']
                g_p1 += pdata['p1']
                g_p0 += pdata['p0']
                g_total += pdata['total']
                
                formatted_lines.append({
                    'id': f"partner_{pid}",
                    'name': pdata['name'],
                    'partner_id': pid,
                    'not_due': pdata['not_due'],
                    'p4': pdata['p4'],
                    'p3': pdata['p3'],
                    'p2': pdata['p2'],
                    'p1': pdata['p1'],
                    'p0': pdata['p0'],
                    'total': pdata['total'],
                    'level': 1,
                    'type': 'group',
                    'action_buttons': [
                        {'label': 'Partner', 'class': 'btn-outline-secondary btn-sm badge-pill me-1', 'action': 'open_partner'},
                        {'label': 'Statement', 'class': 'btn-outline-secondary btn-sm badge-pill', 'action': 'open_statement'},
                    ] if pid else []
                })
                formatted_lines.extend(pdata['lines'])
                
            # Add Total row at bottom
            if formatted_lines:
                formatted_lines.append({
                    'id': 'total',
                    'name': _("Total %s") % result['title'],
                    'not_due': g_not_due,
                    'p4': g_p4,
                    'p3': g_p3,
                    'p2': g_p2,
                    'p1': g_p1,
                    'p0': g_p0,
                    'total': g_total,
                    'level': 1,
                    'type': 'total',
                    'is_summary_total': True,
                })
                
            result['lines'] = formatted_lines
            
        elif model_name == 'account.print.journal':
            result['title'] = _("Journal Audit")
            result['columns'] = [
                {'label': 'Name', 'field': 'name'},
                {'label': 'Documents', 'field': 'docs_count', 'type': 'integer'},
                {'label': 'To Review', 'field': 'draft_count', 'type': 'integer'},
                {'label': 'Debit', 'field': 'debit', 'type': 'monetary'},
                {'label': 'Credit', 'field': 'credit', 'type': 'monetary'},
                {'label': 'Balance', 'field': 'balance', 'type': 'monetary'},
            ]
            
            wizard = self.env[model_name].browse(wizard_id) if wizard_id else False
            if not wizard or not wizard.exists():
                clean_data = {k: v for k, v in form_data.items() if k in self.env[model_name]._fields}
                wizard = self.env[model_name].new(clean_data)
                
            journal_ids = wizard.journal_ids.ids if hasattr(wizard, 'journal_ids') and wizard.journal_ids else form_data.get('journal_ids', [])
            if ledger_journal_ids:
                # Keep only the wizard's journals that belong to the selected ledgers
                journal_ids = [j for j in (journal_ids or ledger_journal_ids) if j in ledger_journal_ids] or [-1]
            target_move = wizard.target_move if hasattr(wizard, 'target_move') and wizard.target_move else form_data.get('target_move', 'posted')
            date_from = wizard.date_from if hasattr(wizard, 'date_from') and wizard.date_from else form_data.get('date_from')
            date_to = wizard.date_to if hasattr(wizard, 'date_to') and wizard.date_to else form_data.get('date_to')

            today = fields.Date.context_today(self)
            if not date_from or not date_to:
                fiscal_dates = self.env.company.compute_fiscalyear_dates(today)
                date_from = date_from or fiscal_dates['date_from']
                date_to = date_to or fiscal_dates['date_to']

            company_ids = (self.env.company.id,)
            
            cr = self.env.cr
            # 1. Journals Summary
            j_query = """
                SELECT 
                    j.id as journal_id,
                    j.name as journal_name,
                    j.code as journal_code,
                    COUNT(DISTINCT CASE WHEN ((%s = 'all' AND m.state = 'draft') OR m.state = 'posted') THEN m.id END) as docs_count,
                    COUNT(DISTINCT CASE WHEN (m.state = 'draft' OR m.review_state = 'todo') THEN m.id END) as draft_count,
                    SUM(CASE WHEN ((%s = 'all' AND m.state = 'draft') OR m.state = 'posted') THEN l.debit ELSE 0 END) as debit,
                    SUM(CASE WHEN ((%s = 'all' AND m.state = 'draft') OR m.state = 'posted') THEN l.credit ELSE 0 END) as credit,
                    SUM(CASE WHEN ((%s = 'all' AND m.state = 'draft') OR m.state = 'posted') THEN l.balance ELSE 0 END) as balance
                FROM account_move_line l
                JOIN account_move m ON l.move_id = m.id
                JOIN account_journal j ON l.journal_id = j.id
                WHERE l.display_type NOT IN ('line_section', 'line_note')
                  AND l.company_id IN %s
            """
            j_params = [target_move, target_move, target_move, target_move, company_ids]
            if journal_ids:
                j_query += " AND l.journal_id IN %s"
                j_params.append(tuple(journal_ids))
            if date_from:
                j_query += " AND l.date >= %s"
                j_params.append(date_from)
            if date_to:
                j_query += " AND l.date <= %s"
                j_params.append(date_to)
                
            j_query += " GROUP BY j.id, j.name, j.code, j.sequence ORDER BY j.sequence, j.name"
            cr.execute(j_query, tuple(j_params))
            journals_data = cr.dictfetchall()
            
            # 2. Accounts Summary (Child of Journal)
            a_query = """
                SELECT 
                    j.id as journal_id,
                    a.id as account_id,
                    SUM(l.debit) as debit,
                    SUM(l.credit) as credit,
                    SUM(l.balance) as balance
                FROM account_move_line l
                JOIN account_move m ON l.move_id = m.id
                JOIN account_journal j ON l.journal_id = j.id
                JOIN account_account a ON l.account_id = a.id
                WHERE l.display_type NOT IN ('line_section', 'line_note')
                  AND l.company_id IN %s
            """
            a_params = [company_ids]
            if target_move == 'posted':
                a_query += " AND m.state = 'posted'"
            else:
                a_query += " AND m.state IN ('draft', 'posted')"
            if journal_ids:
                a_query += " AND l.journal_id IN %s"
                a_params.append(tuple(journal_ids))
            if date_from:
                a_query += " AND l.date >= %s"
                a_params.append(date_from)
            if date_to:
                a_query += " AND l.date <= %s"
                a_params.append(date_to)
                
            a_query += " GROUP BY j.id, a.id"
            cr.execute(a_query, tuple(a_params))
            accounts_data = cr.dictfetchall()
            
            account_ids = [a['account_id'] for a in accounts_data]
            accounts = self.env['account.account'].browse(account_ids)
            account_map = {acc.id: {'code': acc.code, 'name': acc.name} for acc in accounts}
            
            formatted_lines = []
            
            for j in journals_data:
                j_name = j['journal_name']
                if isinstance(j_name, dict):
                    j_name = j_name.get(self.env.lang) or next(iter(j_name.values()), '')

                # Add Journal Group Row
                formatted_lines.append({
                    'id': f"journal_{j['journal_id']}",
                    'name': f"{j_name} {j['journal_code']}",
                    'docs_count': j['docs_count'],
                    'draft_count': j['draft_count'],
                    'debit': j['debit'] or 0.0,
                    'credit': j['credit'] or 0.0,
                    'balance': '',  # Blank for journal level matching Odoo Online
                    'level': 1,
                    'type': 'group',
                    'journal_id': j['journal_id'],
                    'action_buttons': [
                        {'label': 'Audit', 'class': 'o_audit_badge ms-2', 'action': 'open_journal_items'},
                    ]
                })
                
                # Accounts inside this Journal
                j_accounts = [a for a in accounts_data if a['journal_id'] == j['journal_id']]
                
                # Sort j_accounts by account code
                j_accounts = sorted(j_accounts, key=lambda a: account_map.get(a['account_id'], {}).get('code') or '')
                
                for a in j_accounts:
                    acc_info = account_map.get(a['account_id'], {'code': '', 'name': ''})
                    acc_name = acc_info['name']
                    if isinstance(acc_name, dict):
                        acc_name = acc_name.get(self.env.lang) or next(iter(acc_name.values()), '')
                    formatted_lines.append({
                        'id': f"account_{j['journal_id']}_{a['account_id']}",
                        'name': f"{acc_info['code'] or ''} {acc_name}".strip(),
                        'docs_count': '',
                        'draft_count': '',
                        'debit': a['debit'] or 0.0,
                        'credit': a['credit'] or 0.0,
                        'balance': a['balance'] or 0.0,
                        'level': 2,
                        'type': 'account',
                        'account_id': a['account_id'],
                        'journal_id': j['journal_id'],
                    })
            
            result['lines'] = formatted_lines
            result['date_from'] = str(date_from) if date_from else False
            result['date_to'] = str(date_to) if date_to else False
            result['target_move'] = target_move
        elif model_name in ('account.deferred.revenue.report', 'account.deferred.expense.report'):
            is_revenue = (model_name == 'account.deferred.revenue.report')
            result['title'] = _("Deferred Revenues") if is_revenue else _("Deferred Expenses")
            
            # Active companies string
            result['companies_description'] = ", ".join(self.env.companies.mapped('name'))
            
            # Date resolution
            today = fields.Date.context_today(self)
            date_from_raw = form_data.get('date_from')
            date_to_raw = form_data.get('date_to')
            
            if date_from_raw:
                p_start = fields.Date.from_string(date_from_raw) if isinstance(date_from_raw, str) else date_from_raw
            else:
                p_start = today.replace(day=1)
                
            if date_to_raw:
                p_end = fields.Date.from_string(date_to_raw) if isinstance(date_to_raw, str) else date_to_raw
            else:
                p_end = (p_start + relativedelta(months=1, days=-1))
                
            # Period column label matching enterprise screenshot (e.g. 'Jul 2026' or '01/10/2026 - 15/10/2026')
            if p_start.day == 1 and (p_end + relativedelta(days=1)).day == 1 and p_start.month == p_end.month and p_start.year == p_end.year:
                period_col_label = p_start.strftime('%b %Y')
            elif p_start.day == 1 and (p_end + relativedelta(days=1)).day == 1:
                period_col_label = f"{p_start.strftime('%b %Y')} - {p_end.strftime('%b %Y')}"
            else:
                period_col_label = f"{p_start.strftime('%d/%m/%Y')} - {p_end.strftime('%d/%m/%Y')}"
                
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': _('Total'), 'field': 'total', 'type': 'monetary'},
                {'label': _('Not Started'), 'field': 'not_started', 'type': 'monetary'},
                {'label': _('Before'), 'field': 'before', 'type': 'monetary'},
                {'label': period_col_label, 'field': 'period', 'type': 'monetary'},
                {'label': _('Recognized'), 'field': 'recognized', 'type': 'monetary'},
                {'label': _('Later'), 'field': 'later', 'type': 'monetary'},
            ]
            
            # Unposted Journal Entries Alert Banner
            unposted_count = self.env['account.move'].search_count([
                ('state', '=', 'draft'),
                ('company_id', 'in', self.env.companies.ids),
                ('date', '<=', p_end)
            ])
            if unposted_count > 0:
                result['alert_message'] = _('There are unposted Journal Entries prior or included in this period.')

            # Target account types
            if is_revenue:
                target_account_types = ('income', 'income_other')
            else:
                target_account_types = ('expense', 'expense_direct_cost', 'expense_depreciation')

            # Search deferral lines from invoice lines
            line_domain = [
                ('company_id', 'in', self.env.companies.ids),
                ('account_id.account_type', 'in', target_account_types),
                ('hudson_deferred_start_date', '!=', False),
                ('hudson_deferred_end_date', '!=', False),
            ]
            
            if form_data.get('target_move') == 'posted':
                line_domain.append(('move_id.state', '=', 'posted'))
            else:
                line_domain.append(('move_id.state', 'in', ('posted', 'draft')))

            if form_data.get('partner_ids'):
                line_domain.append(('partner_id', 'in', form_data['partner_ids']))
            if ledger_journal_ids:
                line_domain.append(('journal_id', 'in', ledger_journal_ids))

            deferral_lines = self.env['account.move.line'].search(line_domain, order='account_id, move_id, id')
            
            # Group lines by account
            account_groups = {}
            for line in deferral_lines:
                acc = line.account_id
                if acc.id not in account_groups:
                    account_groups[acc.id] = {
                        'account': acc,
                        'lines': []
                    }
                account_groups[acc.id]['lines'].append(line)
                
            formatted_lines = []
            grand_total = 0.0
            grand_not_started = 0.0
            grand_before = 0.0
            grand_period = 0.0
            grand_recognized = 0.0
            grand_later = 0.0
            
            for acc_id, group in account_groups.items():
                acc = group['account']
                acc_total = 0.0
                acc_not_started = 0.0
                acc_before = 0.0
                acc_period = 0.0
                acc_recognized = 0.0
                acc_later = 0.0
                
                child_lines = []
                for line in group['lines']:
                    # Calculate total line amount
                    amount = abs(line.balance)
                    d_start = line.hudson_deferred_start_date
                    d_end = line.hudson_deferred_end_date
                    total_days = max(1, (d_end - d_start).days + 1)
                    
                    if d_start > p_end:
                        # Deferral starts after current period
                        l_not_started = amount
                        l_before = 0.0
                        l_period = 0.0
                        l_recognized = 0.0
                        l_later = 0.0
                    else:
                        l_not_started = 0.0
                        # Portion before p_start
                        if d_start < p_start:
                            end_before = min(d_end, p_start - relativedelta(days=1))
                            days_before = (end_before - d_start).days + 1
                            l_before = round(amount * (days_before / total_days), 2)
                        else:
                            l_before = 0.0
                            
                        # Portion in current period [p_start, p_end]
                        overlap_start = max(d_start, p_start)
                        overlap_end = min(d_end, p_end)
                        if overlap_start <= overlap_end:
                            days_period = (overlap_end - overlap_start).days + 1
                            l_period = round(amount * (days_period / total_days), 2)
                        else:
                            l_period = 0.0
                            
                        l_recognized = round(l_before + l_period, 2)
                        
                        # Portion later (after p_end)
                        if d_end > p_end:
                            l_later = max(0.0, round(amount - l_before - l_period, 2))
                        else:
                            l_later = 0.0

                    acc_total += amount
                    acc_not_started += l_not_started
                    acc_before += l_before
                    acc_period += l_period
                    acc_recognized += l_recognized
                    acc_later += l_later

                    line_title = f"{line.move_id.name}"
                    if line.name and line.name != line.move_id.name:
                        line_title += f" - {line.name}"
                    elif line.product_id:
                        line_title += f" - {line.product_id.name}"

                    child_lines.append({
                        'id': f"mline_{line.id}",
                        'name': line_title,
                        'partner': line.partner_id.name or '',
                        'total': amount,
                        'not_started': l_not_started,
                        'before': l_before,
                        'period': l_period,
                        'recognized': l_recognized,
                        'later': l_later,
                        'level': 2,
                        'type': 'move_line',
                        'move_id': line.move_id.id,
                        'move_line_id': line.id,
                        'move_type': line.move_id.move_type,
                        'action_buttons': [
                            {'label': _('Journal Items'), 'action': 'open_journal_items'}
                        ]
                    })
                
                # Account Level 1 Line
                formatted_lines.append({
                    'id': f"acc_{acc.id}",
                    'name': f"{acc.code} {acc.name}" if acc.code else (acc.name or ''),
                    'total': acc_total,
                    'not_started': acc_not_started,
                    'before': acc_before,
                    'period': acc_period,
                    'recognized': acc_recognized,
                    'later': acc_later,
                    'level': 1,
                    'type': 'account',
                    'account_id': acc.id,
                    'action_buttons': [{'label': _('Journal Items'), 'action': 'open_journal_items'}]
                })
                formatted_lines.extend(child_lines)
                
                grand_total += acc_total
                grand_not_started += acc_not_started
                grand_before += acc_before
                grand_period += acc_period
                grand_recognized += acc_recognized
                grand_later += acc_later

            # Grand Total Summary Row
            formatted_lines.append({
                'id': 'total',
                'name': _('Total'),
                'total': grand_total,
                'not_started': grand_not_started,
                'before': grand_before,
                'period': grand_period,
                'recognized': grand_recognized,
                'later': grand_later,
                'level': 1,
                'type': 'total',
                'is_summary_total': True,
            })
            
            result['lines'] = formatted_lines
            result['date_from'] = fields.Date.to_string(p_start) if p_start else False
            result['date_to'] = fields.Date.to_string(p_end) if p_end else False
            result['target_move'] = form_data.get('target_move', 'posted')
        elif model_name == 'account.analytic.report':
            result['title'] = _("Analytic Report")
            result['companies_description'] = ", ".join(self.env.companies.mapped('name'))
            
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': _('Date'), 'field': 'date'},
                {'label': _('Partner'), 'field': 'partner'},
                {'label': _('Financial Account'), 'field': 'general_account'},
                {'label': _('Product / Task'), 'field': 'product_task'},
                {'label': _('Quantity'), 'field': 'unit_amount'},
                {'label': _('Amount'), 'field': 'amount', 'type': 'monetary'},
            ]
            
            date_from = form_data.get('date_from')
            date_to = form_data.get('date_to')
            
            if date_to:
                unposted_count = self.env['account.move'].search_count([
                    ('state', '=', 'draft'),
                    ('company_id', 'in', self.env.companies.ids),
                    ('date', '<=', date_to)
                ])
                if unposted_count > 0:
                    result['alert_message'] = _('There are unposted Journal Entries prior or included in this period.')

            domain = [('company_id', 'in', self.env.companies.ids)]
            if date_from:
                domain.append(('date', '>=', date_from))
            if date_to:
                domain.append(('date', '<=', date_to))
            if form_data.get('partner_ids'):
                domain.append(('partner_id', 'in', form_data['partner_ids']))
            analytic_filter_ids = form_data.get('analytic_account_ids') or form_data.get('analytic_accounts')
            if analytic_filter_ids:
                domain.append(('account_id', 'in', analytic_filter_ids))
            if ledger_journal_ids:
                # Only analytic lines generated from journal items of the selected ledgers
                domain.append(('move_line_id.journal_id', 'in', ledger_journal_ids))

            lines = self.env['account.analytic.line'].search(domain, order='account_id, date desc, id desc')
            
            grouped_data = {}
            for l in lines:
                acc = l.account_id
                acc_key = acc.id if acc else 0
                plan_name = acc.plan_id.name if acc and acc.plan_id else 'Project'
                acc_name = f"{plan_name}: {acc.name if acc else _('No Analytic Account')}"
                if acc_key not in grouped_data:
                    grouped_data[acc_key] = {
                        'name': acc_name,
                        'account': acc,
                        'lines': [],
                        'total_amount': 0.0,
                        'total_qty': 0.0,
                    }
                grouped_data[acc_key]['lines'].append(l)
                grouped_data[acc_key]['total_amount'] += (l.amount or 0.0)
                grouped_data[acc_key]['total_qty'] += (l.unit_amount or 0.0)
                
            formatted_lines = []
            grand_total_amount = 0.0
            grand_total_qty = 0.0
            
            for acc_key, group in grouped_data.items():
                acc = group['account']
                formatted_lines.append({
                    'id': f"plan_acc_{acc_key}",
                    'name': group['name'],
                    'date': '',
                    'partner': '',
                    'general_account': '',
                    'product_task': '',
                    'unit_amount': round(group['total_qty'], 2),
                    'amount': round(group['total_amount'], 2),
                    'level': 1,
                    'type': 'account',
                    'account_id': acc.id if acc else False,
                    'action_buttons': [{'label': _('Journal Items'), 'action': 'open_journal_items'}]
                })
                
                for l in group['lines']:
                    prod_task = l.product_id.name if l.product_id else (l.task_id.name if l.task_id else (l.project_id.name if l.project_id else ''))
                    formatted_lines.append({
                        'id': f"aline_{l.id}",
                        'name': l.name or '/',
                        'date': l.date.strftime('%d/%m/%Y') if l.date else '',
                        'partner': l.partner_id.name or '',
                        'general_account': (f"{l.general_account_id.code} {l.general_account_id.name}" if l.general_account_id.code else (l.general_account_id.name or '')) if l.general_account_id else '',
                        'product_task': prod_task,
                        'unit_amount': round(l.unit_amount or 0.0, 2),
                        'amount': round(l.amount or 0.0, 2),
                        'level': 2,
                        'type': 'move_line',
                        'move_id': l.move_line_id.move_id.id if l.move_line_id else False,
                        'move_line_id': l.move_line_id.id if l.move_line_id else False,
                        'action_buttons': [{'label': _('Journal Items'), 'action': 'open_journal_items'}]
                    })
                    
                grand_total_amount += group['total_amount']
                grand_total_qty += group['total_qty']
                
            formatted_lines.append({
                'id': 'total',
                'name': _('Total'),
                'date': '',
                'partner': '',
                'general_account': '',
                'product_task': '',
                'unit_amount': round(grand_total_qty, 2),
                'amount': round(grand_total_amount, 2),
                'level': 1,
                'type': 'total',
                'is_summary_total': True,
            })
            
            result['lines'] = formatted_lines
            result['date_from'] = str(date_from) if date_from else False
            result['date_to'] = str(date_to) if date_to else False
            result['target_move'] = form_data.get('target_move', 'posted')
        elif model_name in ('account.unrealized.currency.wizard', 'account.unrealized.currency.report'):
            result['title'] = _("Unrealized Currency Gains/Losses")
            result['companies_description'] = ", ".join(self.env.companies.mapped('name'))
            result['secondary_alert_message'] = _("This report only displays the data of the active company.")
            
            result['columns'] = [
                {'label': '', 'field': 'name'},
                {'label': _('Balance in Foreign Currency'), 'field': 'amount_currency', 'type': 'monetary'},
                {'label': _('Balance at Operation Rate'), 'field': 'operation_balance', 'type': 'monetary'},
                {'label': _('Balance at Current Rate'), 'field': 'current_balance', 'type': 'monetary'},
                {'label': _('Adjustment'), 'field': 'adjustment', 'type': 'monetary'},
            ]
            
            company = self.env.company
            as_of = form_data.get('date_to') or form_data.get('as_of_date') or form_data.get('date_from') or fields.Date.context_today(self)
            
            # Unposted Notice Alert
            unposted_count = self.env['account.move'].search_count([
                ('state', '=', 'draft'),
                ('company_id', '=', company.id),
                ('date', '<=', as_of)
            ])
            if unposted_count > 0:
                result['alert_message'] = _('There are unposted Journal Entries prior or included in this period.')
                
            domain = [
                ('company_id', '=', company.id),
                ('date', '<=', as_of),
                ('reconciled', '=', False),
                ('currency_id', '!=', False),
                ('currency_id', '!=', company.currency_id.id),
                ('account_id.account_type', 'in', [
                    'asset_receivable', 'liability_payable',
                    'asset_current', 'liability_current',
                    'asset_prepayments', 'liability_credit_card',
                    'asset_non_current', 'liability_non_current',
                    'asset_cash'
                ])
            ]
            if form_data.get('target_move') == 'posted':
                domain.append(('parent_state', '=', 'posted'))
            else:
                domain.append(('parent_state', 'in', ('posted', 'draft')))
            if ledger_journal_ids:
                domain.append(('journal_id', 'in', ledger_journal_ids))

            lines = self.env['account.move.line'].search(domain, order='account_id, date desc, id desc')
            
            by_currency = {}
            for l in lines:
                curr = l.currency_id
                if curr not in by_currency:
                    rate_record = self.env['res.currency.rate'].search([
                        ('currency_id', '=', curr.id),
                        ('name', '<=', as_of),
                        ('company_id', '=', company.id),
                    ], order='name desc', limit=1)
                    
                    if rate_record and rate_record.rate:
                        curr_rate = rate_record.rate
                    else:
                        curr_rate = curr.rate or 1.0
                        
                    by_currency[curr] = {
                        'currency': curr,
                        'rate': curr_rate,
                        'accounts': {},
                        'total_foreign': 0.0,
                        'total_op': 0.0,
                        'total_curr': 0.0,
                        'total_adj': 0.0,
                    }
                    
                acc = l.account_id
                if acc not in by_currency[curr]['accounts']:
                    by_currency[curr]['accounts'][acc] = {
                        'account': acc,
                        'lines': [],
                        'total_foreign': 0.0,
                        'total_op': 0.0,
                        'total_curr': 0.0,
                        'total_adj': 0.0,
                    }
                    
                foreign_amt = l.amount_residual_currency or l.amount_currency or 0.0
                if abs(foreign_amt) < 0.0001:
                    continue
                    
                op_bal = l.amount_residual if l.amount_residual else (l.debit - l.credit)
                curr_bal = curr._convert(foreign_amt, company.currency_id, company, as_of)
                adj = curr_bal - op_bal
                
                by_currency[curr]['accounts'][acc]['lines'].append({
                    'line': l,
                    'foreign_amt': foreign_amt,
                    'op_bal': op_bal,
                    'curr_bal': curr_bal,
                    'adj': adj,
                })
                
                by_currency[curr]['accounts'][acc]['total_foreign'] += foreign_amt
                by_currency[curr]['accounts'][acc]['total_op'] += op_bal
                by_currency[curr]['accounts'][acc]['total_curr'] += curr_bal
                by_currency[curr]['accounts'][acc]['total_adj'] += adj
                
                by_currency[curr]['total_foreign'] += foreign_amt
                by_currency[curr]['total_op'] += op_bal
                by_currency[curr]['total_curr'] += curr_bal
                by_currency[curr]['total_adj'] += adj

            formatted_lines = []
            
            # Header Section
            formatted_lines.append({
                'id': 'header_section',
                'name': _('Accounts To Adjust'),
                'amount_currency': '',
                'operation_balance': '',
                'current_balance': '',
                'adjustment': '',
                'level': 1,
                'type': 'section_header',
            })
            
            for curr, c_data in by_currency.items():
                curr_rate = c_data['rate']
                rate_str = f"{curr.name} (1 {company.currency_id.name} = {curr_rate:.7f} {curr.name})"
                
                formatted_lines.append({
                    'id': f"curr_{curr.id}",
                    'name': rate_str,
                    'foreign_currency_symbol': curr.symbol,
                    'amount_currency': '',
                    'operation_balance': '',
                    'current_balance': '',
                    'adjustment': '',
                    'level': 1,
                    'type': 'currency_group',
                    'action_buttons': [{'label': _('Exchange Rates'), 'action': 'open_exchange_rates'}]
                })
                
                for acc, a_data in c_data['accounts'].items():
                    acc_label = f"{acc.code} {acc.name}" if acc.code else (acc.name or '')
                    formatted_lines.append({
                        'id': f"acc_{curr.id}_{acc.id}",
                        'name': acc_label,
                        'foreign_currency_symbol': curr.symbol,
                        'amount_currency': '',
                        'operation_balance': '',
                        'current_balance': '',
                        'adjustment': '',
                        'level': 2,
                        'type': 'account',
                        'account_id': acc.id,
                        'action_buttons': [
                            {'label': _('General Ledger'), 'action': 'open_general_ledger'},
                            {'label': _('Journal Items'), 'action': 'open_journal_items'}
                        ]
                    })
                    
                    for item in a_data['lines']:
                        l = item['line']
                        move_name = l.move_id.name or l.name or f"Line #{l.id}"
                        partner_name = f" - {l.partner_id.name}" if l.partner_id else ""
                        line_title = f"{move_name}{partner_name}"
                        
                        formatted_lines.append({
                            'id': f"line_{l.id}",
                            'name': line_title,
                            'foreign_currency_symbol': curr.symbol,
                            'amount_currency': round(item['foreign_amt'], 2),
                            'operation_balance': round(item['op_bal'], 2),
                            'current_balance': round(item['curr_bal'], 2),
                            'adjustment': round(item['adj'], 2),
                            'level': 3,
                            'type': 'move_line',
                            'move_id': l.move_id.id,
                            'move_line_id': l.id,
                            'action_buttons': [
                                {'label': _('View Entry'), 'action': 'open_journal_entry'},
                                {'label': _('Journal Items'), 'action': 'open_journal_items'}
                            ]
                        })
                        
                    formatted_lines.append({
                        'id': f"acc_total_{curr.id}_{acc.id}",
                        'name': f"{_('Total')} {acc_label}",
                        'foreign_currency_symbol': curr.symbol,
                        'amount_currency': round(a_data['total_foreign'], 2),
                        'operation_balance': round(a_data['total_op'], 2),
                        'current_balance': round(a_data['total_curr'], 2),
                        'adjustment': round(a_data['total_adj'], 2),
                        'level': 2,
                        'type': 'account_total',
                        'is_summary_total': True,
                    })
                    
                formatted_lines.append({
                    'id': f"curr_total_{curr.id}",
                    'name': f"{_('Total')} {curr.name}",
                    'foreign_currency_symbol': curr.symbol,
                    'amount_currency': round(c_data['total_foreign'], 2),
                    'operation_balance': round(c_data['total_op'], 2),
                    'current_balance': round(c_data['total_curr'], 2),
                    'adjustment': round(c_data['total_adj'], 2),
                    'level': 1,
                    'type': 'currency_total',
                    'is_summary_total': True,
                })
                
            result['lines'] = formatted_lines
        elif model_name == 'asset.depreciation.schedule':
            result['title'] = _("Depreciation Schedule")
            
            wizard = self.env['asset.depreciation.schedule'].browse(wizard_id) if wizard_id else False
            if not wizard or not wizard.exists():
                wizard = self.env['asset.depreciation.schedule'].create({})
                wizard_id = wizard.id

            # Sync dates and category from form_data
            vals_to_write = {}
            if form_data.get('date_from'):
                vals_to_write['date_from'] = form_data['date_from']
            if form_data.get('date_to'):
                vals_to_write['date_to'] = form_data['date_to']
            if form_data.get('category_ids') is not None:
                vals_to_write['category_ids'] = [(6, 0, form_data['category_ids'])]
            if vals_to_write:
                try:
                    wizard.write(vals_to_write)
                except Exception:
                    pass

            df_str = fields.Date.to_string(wizard.date_from)
            dt_str = fields.Date.to_string(wizard.date_to)
            df_label = df_str
            dt_label = dt_str
            if df_str:
                p = df_str.split('-')
                if len(p) == 3:
                    df_label = f"{p[2]}/{p[1]}/{p[0]}"
            if dt_str:
                p = dt_str.split('-')
                if len(p) == 3:
                    dt_label = f"{p[2]}/{p[1]}/{p[0]}"

            result['date_from'] = df_str
            result['date_to'] = dt_str
            result['currency_id'] = wizard.company_id.currency_id.id
            result['company_id'] = wizard.company_id.id

            result['columns'] = [
                {'label': _('Asset'), 'field': 'name'},
                {'label': _('In Service'), 'field': 'in_service'},
                {'label': _('Life'), 'field': 'life'},
                {'label': _('Cost'), 'field': 'cost', 'type': 'monetary'},
                {'label': _('Salvage'), 'field': 'salvage_value', 'type': 'monetary'},
                {'label': (_('NBV at %s') % df_label) if df_label else _('Opening NBV'), 'field': 'nbv_opening', 'type': 'monetary'},
                {'label': _('Depreciation'), 'field': 'depreciation_charge', 'type': 'monetary'},
                {'label': _('Disposed NBV'), 'field': 'disposed_nbv', 'type': 'monetary'},
                {'label': (_('NBV at %s') % dt_label) if dt_label else _('Closing NBV'), 'field': 'nbv_closing', 'type': 'monetary'},
                {'label': _('Depreciated %'), 'field': 'depreciated_percent_str', 'type': 'percentage'},
            ]

            schedule_data = wizard._get_schedule_data()
            formatted_lines = []

            for group in schedule_data.get('register', []):
                totals = group.get('totals', {})
                cat_id_slug = group['name'].replace(' ', '_').lower()

                # Category group header
                formatted_lines.append({
                    'id': f"cat_{cat_id_slug}",
                    'name': group['name'],
                    'in_service': '',
                    'life': '',
                    'cost': totals.get('cost', 0.0),
                    'salvage_value': totals.get('salvage_value', 0.0),
                    'nbv_opening': totals.get('nbv_opening', 0.0),
                    'depreciation_charge': totals.get('depreciation_charge', 0.0),
                    'disposed_nbv': totals.get('disposed_nbv', 0.0),
                    'nbv_closing': totals.get('nbv_closing', 0.0),
                    'depreciated_percent_str': '',
                    'level': 1,
                    'type': 'group',
                })

                # Individual asset rows
                for l in group.get('lines', []):
                    asset = l['asset']
                    asset_display = f"[{l['code']}] {asset.name}" if l.get('code') else asset.name
                    if l.get('is_disposed'):
                        asset_display += _(" (disposed)")
                    elif l.get('is_partly_disposed'):
                        asset_display += _(" (partly disposed)")

                    in_svc = str(asset.date) if asset.date else ''
                    if in_svc:
                        sp = in_svc.split('-')
                        if len(sp) == 3:
                            in_svc = f"{sp[2]}/{sp[1]}/{sp[0]}"

                    formatted_lines.append({
                        'id': f"asset_{asset.id}",
                        'name': asset_display,
                        'in_service': in_svc,
                        'life': l.get('life', ''),
                        'cost': l.get('cost', 0.0),
                        'salvage_value': l.get('salvage_value', 0.0),
                        'nbv_opening': l.get('nbv_opening', 0.0),
                        'depreciation_charge': l.get('depreciation_charge', 0.0),
                        'disposed_nbv': l.get('disposed_nbv', 0.0),
                        'nbv_closing': l.get('nbv_closing', 0.0),
                        'depreciated_percent_str': f"{l.get('depreciated_percent', 0)} %",
                        'level': 2,
                        'type': 'asset',
                        'asset_id': asset.id,
                        'res_model': 'account.asset.asset',
                        'res_id': asset.id,
                        'action_buttons': [{'label': _('View Asset'), 'action': 'open_asset'}],
                    })

            # Grand total
            grand_total = schedule_data.get('total', {})
            formatted_lines.append({
                'id': 'deprec_grand_total',
                'name': _('Total'),
                'in_service': '',
                'life': '',
                'cost': grand_total.get('cost', 0.0),
                'salvage_value': grand_total.get('salvage_value', 0.0),
                'nbv_opening': grand_total.get('nbv_opening', 0.0),
                'depreciation_charge': grand_total.get('depreciation_charge', 0.0),
                'disposed_nbv': grand_total.get('disposed_nbv', 0.0),
                'nbv_closing': grand_total.get('nbv_closing', 0.0),
                'depreciated_percent_str': '',
                'level': 1,
                'type': 'total',
                'is_summary_total': True,
            })

            result['lines'] = formatted_lines
        else:
            result['title'] = _("Report")
            result['columns'] = [{'label': 'Name', 'field': 'name'}]

        if form_data.get('comparison') == 'percentage' or form_data.get('comparison_in') == 'percentage':
            if not any(c.get('type') == 'percentage' for c in result.get('columns', [])):
                is_bs = 'balance sheet' in (result.get('title') or '').lower()
                is_pl = ('profit' in (result.get('title') or '').lower() or 'loss' in (result.get('title') or '').lower())
                self._compute_percentage_comparison(result, form_data, is_pl=is_pl, is_bs=is_bs, cmp_periods_info=cmp_periods_info)

        if 'date_from' not in result:
            result['date_from'] = form_data.get('date_from', False)
        if 'date_to' not in result:
            result['date_to'] = form_data.get('date_to', False)
        if 'target_move' not in result:
            result['target_move'] = form_data.get('target_move', 'posted')

        return result

