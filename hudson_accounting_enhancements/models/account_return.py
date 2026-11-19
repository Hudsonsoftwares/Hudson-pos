import ast
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import date_utils, format_date
from odoo.tools.misc import formatLang

# Workflow of a return type ("States"): the steps shown on the return progress bar.
RETURN_STEPS = {
    'reviewed': [('reviewed', 'Reviewed')],
    'submitted': [('reviewed', 'Reviewed'), ('submitted', 'Submitted')],
    'paid': [('reviewed', 'Reviewed'), ('submitted', 'Submitted'), ('paid', 'Paid')],
}
STATE_ORDER = ['new', 'reviewed', 'submitted', 'paid']


def _serialize_domain(domain):
    """ Dates as strings so the domain can be stored with repr() and read back safely. """
    def convert(value):
        if isinstance(value, date):
            return fields.Date.to_string(value)
        if isinstance(value, (list, tuple)):
            return type(value)(convert(v) for v in value)
        return value
    return [convert(term) for term in domain]


class AccountReturnType(models.Model):
    _name = 'account.return.type'
    _inherit = ['account.return.type', 'mail.thread']
    _order = 'sequence, id'

    name = fields.Char(tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category = fields.Selection([
        ('tax', 'Tax Return'),
        ('annual', 'Audit'),
    ], string="Type", required=True, default='tax', tracking=True,
        help="Tax Return: periodic tax (VAT/GST) return; validating it books the tax closing entry "
             "and sets the tax lock date.\nAudit: closing checklist such as the annual closing.")
    states_workflow = fields.Selection([
        ('reviewed', 'Reviewed'),
        ('submitted', 'Reviewed → Submitted'),
        ('paid', 'Reviewed → Submitted → Paid'),
    ], string="States", required=True, default='reviewed', tracking=True,
        help="Steps a return of this type goes through before it is completed.")
    deadline_start_date = fields.Date(
        string="Start Date", tracking=True,
        help="First day of a period of this return. Periods are counted from this date; "
             "leave empty to start them with the fiscal year.")
    country_id = fields.Many2one(default=False, tracking=True,
                                 help="Leave empty to offer this return type to companies of any country.")
    report_id = fields.Many2one('account.report', string="Report", tracking=True,
                                help="Tax report declared with this return.")
    payment_partner_id = fields.Many2one('res.partner', string="Payment Partner", tracking=True,
                                         help="Tax authority the tax due is paid to.")
    payment_partner_bank_id = fields.Many2one(
        'res.partner.bank', string="Payment Partner Bank", tracking=True,
        domain="[('partner_id', '=', payment_partner_id)]",
        help="Bank account of the tax authority used to pay the tax due.")
    company_id = fields.Many2one('res.company', string="Company",
                                 help="Leave empty to share this return type with all companies.")
    periodicity = fields.Selection(selection_add=[('semester', 'Semi-annually')],
                                   ondelete={'semester': 'set default'}, tracking=True)
    deadline_days_delay = fields.Integer(
        string="Deadline", default=7, tracking=True,
        help="Number of days after the end of the period by which the return is due.")
    auto_generate = fields.Boolean(
        string="Generate Automatically", default=False,
        help="Create the returns of the previous and current periods automatically "
             "when the Tax Returns menu is opened.")
    closing_journal_id = fields.Many2one(
        'account.journal', string="Closing Journal", company_dependent=True,
        domain="[('type', '=', 'general')]",
        help="Journal of the tax closing entry booked when the return is validated.")
    closing_payable_account_id = fields.Many2one(
        'account.account', string="Tax Payable Account", company_dependent=True,
        help="Account that receives the net tax due when the return is validated.")
    closing_receivable_account_id = fields.Many2one(
        'account.account', string="Tax Receivable Account", company_dependent=True,
        help="Account that receives the net tax credit when the return is validated.")
    return_count = fields.Integer(compute='_compute_return_count')

    @api.onchange('payment_partner_id')
    def _onchange_payment_partner_id(self):
        if self.payment_partner_bank_id.partner_id != self.payment_partner_id:
            self.payment_partner_bank_id = self.payment_partner_id.bank_ids[:1]

    @api.onchange('category')
    def _onchange_category(self):
        if self.category == 'annual' and self.states_workflow == 'paid':
            self.states_workflow = 'submitted'

    def _compute_return_count(self):
        counts = dict(self.env['account.return']._read_group(
            [('type_id', 'in', self.ids)], ['type_id'], ['__count']))
        for rtype in self:
            rtype.return_count = counts.get(rtype, 0)

    def _is_available_for(self, company):
        self.ensure_one()
        return (not self.company_id or self.company_id == company) and \
            (not self.country_id or self.country_id == company.account_fiscal_country_id
             or self.country_id == company.country_id)

    @api.model
    def _get_available_types(self, company):
        return self.search([]).filtered(lambda t: t._is_available_for(company))

    # ------------------------------------------------------------------
    # Periods
    # ------------------------------------------------------------------
    def _get_period(self, company, day):
        """ Return (date_from, date_to) of the period of this type containing `day`. """
        self.ensure_one()
        months = {'monthly': 1, 'quarterly': 3, 'semester': 6, 'yearly': 12}.get(self.periodicity, 1)
        if self.deadline_start_date:
            anchor = self.deadline_start_date.replace(day=1)
        elif self.periodicity == 'yearly':
            return date_utils.get_fiscal_year(
                day, day=company.fiscalyear_last_day, month=int(company.fiscalyear_last_month))
        else:
            # Align multi-month periods on the fiscal year start (e.g. Apr-Jun in India).
            fy_start, _fy_end = date_utils.get_fiscal_year(
                day, day=company.fiscalyear_last_day, month=int(company.fiscalyear_last_month))
            anchor = fy_start.replace(day=1)
        diff = (day.year - anchor.year) * 12 + day.month - anchor.month
        start = anchor + relativedelta(months=(diff // months) * months)
        end = start + relativedelta(months=months, days=-1)
        return start, end

    def _get_previous_period(self, company, day):
        start, _end = self._get_period(company, day)
        return self._get_period(company, start - timedelta(days=1))

    def _get_deadline(self, date_to):
        self.ensure_one()
        return date_to + timedelta(days=self.deadline_days_delay or 0)

    def _get_period_label(self, date_from, date_to):
        self.ensure_one()
        if date_from.day == 1 and date_to == date_utils.end_of(date_from, 'month'):
            return format_date(self.env, date_from, date_format='MMM yyyy')
        if date_from.year == date_to.year:
            return '%s - %s' % (format_date(self.env, date_from, date_format='MMM'),
                                format_date(self.env, date_to, date_format='MMM yyyy'))
        return '%s - %s' % (format_date(self.env, date_from, date_format='MMM yyyy'),
                            format_date(self.env, date_to, date_format='MMM yyyy'))


class AccountReturn(models.Model):
    _name = 'account.return'
    _description = "Accounting Return"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, type_id, id desc'
    _check_company_auto = True

    name = fields.Char(compute='_compute_name', store=True, readonly=False, precompute=True,
                       required=True, tracking=True)
    type_id = fields.Many2one('account.return.type', string="Return Type", required=True,
                              ondelete='restrict', index=True)
    category = fields.Selection(related='type_id.category', store=True)
    states_workflow = fields.Selection(related='type_id.states_workflow')
    payment_partner_id = fields.Many2one(related='type_id.payment_partner_id')
    company_id = fields.Many2one('res.company', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(string="From", required=True)
    date_to = fields.Date(string="To", required=True)
    date_deadline = fields.Date(string="Deadline", compute='_compute_date_deadline', store=True, precompute=True,
                                readonly=False, tracking=True)
    state = fields.Selection([
        ('new', 'To Review'),
        ('reviewed', 'Reviewed'),
        ('submitted', 'Submitted'),
        ('paid', 'Paid'),
    ], default='new', required=True, tracking=True, copy=False)
    is_completed = fields.Boolean(string="Completed", tracking=True, copy=False)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one('res.users', string="Responsible", default=lambda self: self.env.user,
                              domain="[('share', '=', False)]", tracking=True)
    check_ids = fields.One2many('account.return.check', 'return_id', string="Checks", copy=False)
    pending_count = fields.Integer(compute='_compute_check_counts', string="Pending Checks")
    anomaly_count = fields.Integer(compute='_compute_check_counts')
    closing_move_id = fields.Many2one('account.move', string="Closing Entry", readonly=True,
                                      copy=False, check_company=True)
    previous_tax_lock_date = fields.Date(readonly=True, copy=False)
    amount_to_pay = fields.Monetary(compute='_compute_amount_to_pay', string="Tax Due",
                                    help="Net tax of the period: positive when tax is due to the "
                                         "authority, negative for a credit.")
    deadline_status = fields.Selection([
        ('done', 'Done'), ('late', 'Late'), ('soon', 'Due Soon'), ('ok', 'On Time'),
    ], compute='_compute_deadline_status')
    progress_steps = fields.Json(compute='_compute_progress_steps')
    checks_data = fields.Json(compute='_compute_checks_data')
    notes = fields.Html()

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for ret in self:
            if ret.date_from > ret.date_to:
                raise ValidationError(_("The start date of a return must be before its end date."))

    @api.constrains('type_id', 'company_id', 'date_from', 'date_to')
    def _check_unique_period(self):
        for ret in self:
            if self.with_context(active_test=False).search_count([
                ('id', '!=', ret.id), ('type_id', '=', ret.type_id.id),
                ('company_id', '=', ret.company_id.id),
                ('date_from', '=', ret.date_from), ('date_to', '=', ret.date_to),
            ]):
                raise ValidationError(_("A %(type)s return already exists for this period.",
                                        type=ret.type_id.name))

    @api.depends('type_id', 'date_from', 'date_to')
    def _compute_name(self):
        for ret in self:
            if ret.type_id and ret.date_from and ret.date_to:
                ret.name = '%s %s' % (ret.type_id.name,
                                      ret.type_id._get_period_label(ret.date_from, ret.date_to))
            elif not ret.name:
                ret.name = ret.type_id.name or _("Tax Return")

    @api.depends('type_id', 'date_to')
    def _compute_date_deadline(self):
        for ret in self:
            if ret.type_id and ret.date_to:
                ret.date_deadline = ret.type_id._get_deadline(ret.date_to)

    @api.depends('check_ids.result')
    def _compute_check_counts(self):
        for ret in self:
            ret.pending_count = len(ret.check_ids.filtered(lambda c: c.result != 'reviewed'))
            ret.anomaly_count = len(ret.check_ids.filtered(lambda c: c.result == 'anomaly'))

    @api.depends('is_completed', 'date_deadline')
    def _compute_deadline_status(self):
        today = fields.Date.context_today(self)
        for ret in self:
            if ret.is_completed:
                ret.deadline_status = 'done'
            elif not ret.date_deadline:
                ret.deadline_status = 'ok'
            elif ret.date_deadline < today:
                ret.deadline_status = 'late'
            elif ret.date_deadline <= today + timedelta(days=7):
                ret.deadline_status = 'soon'
            else:
                ret.deadline_status = 'ok'

    @api.depends('state', 'states_workflow', 'is_completed')
    def _compute_progress_steps(self):
        for ret in self:
            current = STATE_ORDER.index(ret.state)
            ret.progress_steps = [{
                'key': key,
                'label': label,
                'done': STATE_ORDER.index(key) <= current,
            } for key, label in RETURN_STEPS.get(ret.states_workflow or 'reviewed')]

    @api.depends('check_ids', 'check_ids.result', 'check_ids.notes', 'check_ids.reviewed_by_id')
    def _compute_checks_data(self):
        for ret in self:
            ret.checks_data = [check._get_card_data() for check in ret.check_ids]

    @api.depends('closing_move_id', 'date_from', 'date_to', 'company_id', 'category')
    def _compute_amount_to_pay(self):
        for ret in self:
            if ret.category != 'tax' or not ret.date_from or not ret.date_to:
                ret.amount_to_pay = 0.0
            elif ret.closing_move_id:
                ret.amount_to_pay = -sum(ret.closing_move_id.line_ids.filtered(
                    lambda l: l.account_id in ret._get_closing_counterpart_accounts()).mapped('balance'))
            else:
                # Tax lines carry a credit for tax collected and a debit for deductible tax.
                ret.amount_to_pay = -sum(ret._get_tax_lines().mapped('balance'))

    def _get_closing_counterpart_accounts(self):
        self.ensure_one()
        rtype = self.type_id.with_company(self.company_id)
        return rtype.closing_payable_account_id | rtype.closing_receivable_account_id

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        returns = super().create(vals_list)
        returns._refresh_checks()
        return returns

    def unlink(self):
        for ret in self:
            if ret.state != 'new':
                raise UserError(_("%s has already been validated. Reset it to draft before deleting it.",
                                  ret.name))
        return super().unlink()

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    @api.model
    def _generate_periodic_returns(self, companies=None):
        """ Create the returns of the previous and current periods for every return type set to
        generate automatically. Existing returns (even archived) are never duplicated. """
        companies = companies or self.env.companies
        today = fields.Date.context_today(self)
        to_create = []
        for company in companies:
            for rtype in self.env['account.return.type'].with_company(company)._get_available_types(company):
                if not rtype.auto_generate:
                    continue
                for date_from, date_to in {rtype._get_previous_period(company, today),
                                           rtype._get_period(company, today)}:
                    exists = self.with_context(active_test=False).search_count([
                        ('type_id', '=', rtype.id), ('company_id', '=', company.id),
                        ('date_from', '=', date_from), ('date_to', '=', date_to),
                    ])
                    if not exists:
                        to_create.append({'type_id': rtype.id, 'company_id': company.id,
                                          'date_from': date_from, 'date_to': date_to})
        return self.sudo().create(to_create) if to_create else self.browse()

    @api.model
    def action_open_returns(self):
        """ Entry point of the Tax Returns menu. """
        if self.env.user.has_group('account.group_account_user'):
            self._generate_periodic_returns()
        return self.env['ir.actions.act_window']._for_xml_id(
            'hudson_accounting_enhancements.action_account_return')

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------
    def _period_domain(self, date_field='date'):
        self.ensure_one()
        return [(date_field, '>=', self.date_from), (date_field, '<=', self.date_to)]

    def _get_check_definitions(self):
        """ Checklist of the return. `compute` returns the domain of the records that need
        attention on `model` (empty search result means the check passes); checks without
        `compute` must be reviewed manually. """
        self.ensure_one()
        company_dom = [('company_id', '=', self.company_id.id)]
        draft_moves = {
            'code': 'draft_entries',
            'name': _("Draft Entries"),
            'message': _("Post or delete the draft journal entries of the period."),
            'model': 'account.move',
            'compute': lambda: company_dom + self._period_domain() + [('state', '=', 'draft')],
        }
        bank_rec = {
            'code': 'bank_reconciliation',
            'name': _("Bank Reconciliation"),
            'message': _("Reconcile all bank account transactions up to the end of the period."),
            'model': 'account.bank.statement.line',
            'compute': lambda: company_dom + [('date', '<=', self.date_to),
                                              ('is_reconciled', '=', False),
                                              ('state', '=', 'posted')],
        }
        if self.category == 'annual':
            checks = [
                {
                    'code': 'aged_payable_partner',
                    'name': _("Aged payables per partner"),
                    'message': _("Review payables without a partner."),
                    'model': 'account.move.line',
                    'compute': lambda: company_dom + [
                        ('account_id.account_type', '=', 'liability_payable'),
                        ('partner_id', '=', False), ('parent_state', '=', 'posted'),
                        ('date', '<=', self.date_to), ('reconciled', '=', False),
                    ],
                },
                {
                    'code': 'aged_receivable_partner',
                    'name': _("Aged receivables per partner"),
                    'message': _("Review receivables without a partner."),
                    'model': 'account.move.line',
                    'compute': lambda: company_dom + [
                        ('account_id.account_type', '=', 'asset_receivable'),
                        ('partner_id', '=', False), ('parent_state', '=', 'posted'),
                        ('date', '<=', self.date_to), ('reconciled', '=', False),
                    ],
                },
                dict(bank_rec, message=_("Reconcile all bank account transactions up to year-end.")),
                {
                    'code': 'deferred_entries',
                    'name': _("Deferred Entries"),
                    'message': _("Make sure prepaid expenses and deferred revenues are spread over the "
                                 "right periods. Ensure start and end dates are correctly set on your "
                                 "bills and invoices."),
                },
                {
                    'code': 'earnings_allocation',
                    'name': _("Earnings Allocation"),
                    'message': _("After adjustments, transfer the undistributed Profits/Losses to an "
                                 "equity account."),
                },
                {
                    'code': 'fixed_assets',
                    'name': _("Fixed Assets"),
                    'message': _("Post all depreciation entries up to year-end."),
                    'model': 'account.move',
                    'compute': (lambda: company_dom + [('depreciation_asset_id', '!=', False),
                                                       ('state', '=', 'draft'),
                                                       ('date', '<=', self.date_to)])
                    if 'depreciation_asset_id' in self.env['account.move']._fields else None,
                },
                dict(draft_moves, message=_("Post or delete the draft journal entries of the fiscal year.")),
                {
                    'code': 'bank_suspense',
                    'name': _("Bank Suspense Account"),
                    'message': _("The bank suspense accounts must have a zero balance at year-end."),
                    'model': 'account.move.line',
                    'compute': self._suspense_lines_domain,
                },
                {
                    'code': 'inventory_valuation',
                    'name': _("Inventory Valuation"),
                    'message': _("Check that the stock valuation matches the balance of the inventory "
                                 "accounts."),
                },
                {
                    'code': 'corporate_tax',
                    'name': _("Corporate Tax"),
                    'message': _("Book the corporate income tax expense and the related liability."),
                },
            ]
        else:
            checks = [
                draft_moves,
                bank_rec,
                {
                    'code': 'lines_without_tax',
                    'name': _("Invoice lines without taxes"),
                    'message': _("Review the invoice and bill lines of the period that have no tax."),
                    'model': 'account.move.line',
                    'compute': lambda: company_dom + self._period_domain() + [
                        ('parent_state', '=', 'posted'), ('display_type', '=', 'product'),
                        ('move_id.move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
                        ('tax_ids', '=', False),
                    ],
                },
                {
                    'code': 'partner_vat',
                    'name': _("Companies without Tax ID"),
                    'message': _("Business partners invoiced in the period should have a Tax ID."),
                    'model': 'account.move',
                    'compute': lambda: company_dom + self._period_domain() + [
                        ('state', '=', 'posted'),
                        ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
                        ('commercial_partner_id.is_company', '=', True),
                        ('commercial_partner_id.vat', '=', False),
                    ],
                },
                {
                    'code': 'tax_report',
                    'name': _("Tax Report"),
                    'message': _("Review the tax report of the period and reconcile it with the "
                                 "amounts to declare."),
                    'action': 'hudson_accounting_enhancements.action_server_report_tax',
                },
                {
                    'code': 'closing_settings',
                    'name': _("Closing Accounts"),
                    'message': _("Set the closing journal and the tax payable / receivable accounts on "
                                 "the return type."),
                    'model': 'account.return.type',
                    'compute': self._closing_settings_domain,
                },
            ]
        return [c for c in checks if 'compute' not in c or c['compute']]

    def _suspense_lines_domain(self):
        journals = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id), ('type', 'in', ('bank', 'cash')),
            ('suspense_account_id', '!=', False),
        ])
        accounts = journals.suspense_account_id
        if not accounts:
            return [('id', '=', 0)]
        domain = [('company_id', '=', self.company_id.id), ('account_id', 'in', accounts.ids),
                  ('parent_state', '=', 'posted'), ('date', '<=', self.date_to)]
        balance = sum(self.env['account.move.line'].search(domain).mapped('balance'))
        if self.company_id.currency_id.is_zero(balance):
            return [('id', '=', 0)]
        return domain + [('reconciled', '=', False)]

    def _closing_settings_domain(self):
        rtype = self.type_id.with_company(self.company_id)
        ok = rtype.closing_journal_id and rtype.closing_payable_account_id \
            and rtype.closing_receivable_account_id
        return [('id', '=', 0 if ok else rtype.id)]

    def _refresh_checks(self):
        Check = self.env['account.return.check'].sudo()
        bot = self.env.ref('base.user_root')
        for ret in self:
            existing = {c.code: c for c in ret.check_ids}
            for seq, definition in enumerate(ret._get_check_definitions()):
                check = existing.pop(definition['code'], None)
                vals = {
                    'name': definition['name'],
                    'message': definition['message'],
                    'sequence': seq,
                    'is_automatic': bool(definition.get('compute')),
                    'records_model': definition.get('model', False),
                    'action_xmlid': definition.get('action', False),
                }
                count, domain = 0, False
                if definition.get('compute'):
                    domain = _serialize_domain(definition['compute']())
                    count = self.env[definition['model']].sudo().search_count(domain)
                    vals.update(records_count=count, records_domain=repr(domain))
                if not check:
                    check = Check.create(dict(vals, return_id=ret.id, code=definition['code']))
                else:
                    check.write(vals)
                if check.manually_set:
                    continue
                if definition.get('compute'):
                    if count:
                        check.write({'result': 'anomaly', 'reviewed_by_id': False})
                    else:
                        check.write({'result': 'reviewed', 'reviewed_by_id': bot.id})
            for obsolete in existing.values():
                obsolete.unlink()

    # ------------------------------------------------------------------
    # Tax closing
    # ------------------------------------------------------------------
    def _get_tax_lines(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('tax_line_id', '!=', False),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ]
        if self.closing_move_id:
            domain.append(('move_id', '!=', self.closing_move_id.id))
        return self.env['account.move.line'].search(domain)

    def _prepare_closing_move_vals(self):
        self.ensure_one()
        rtype = self.type_id.with_company(self.company_id)
        currency = self.company_id.currency_id
        if not (rtype.closing_journal_id and rtype.closing_payable_account_id
                and rtype.closing_receivable_account_id):
            raise UserError(_(
                "Configure the closing journal and the tax payable/receivable accounts of the "
                "return type \"%s\" for %s first (Accounting > Configuration > Return Types).",
                rtype.name, self.company_id.name))
        balances = {}
        for line in self._get_tax_lines():
            balances[line.account_id] = balances.get(line.account_id, 0.0) + line.balance
        line_vals = []
        total = 0.0
        for account, balance in balances.items():
            if currency.is_zero(balance):
                continue
            total += balance
            line_vals.append({
                'name': _("Tax closing %s", self.type_id._get_period_label(self.date_from, self.date_to)),
                'account_id': account.id,
                'debit': -balance if balance < 0 else 0.0,
                'credit': balance if balance > 0 else 0.0,
            })
        if not line_vals:
            return False
        # total < 0: more tax collected than deductible -> tax due (credit the payable account).
        counterpart = rtype.closing_payable_account_id if total < 0 else rtype.closing_receivable_account_id
        line_vals.append({
            'name': _("Tax due") if total < 0 else _("Tax credit"),
            'account_id': counterpart.id,
            'debit': total if total > 0 else 0.0,
            'credit': -total if total < 0 else 0.0,
        })
        return {
            'move_type': 'entry',
            'journal_id': rtype.closing_journal_id.id,
            'company_id': self.company_id.id,
            'date': self.date_to,
            'ref': self.name,
            'line_ids': [(0, 0, vals) for vals in line_vals],
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_review(self):
        self.ensure_one()
        if self.state == 'new':
            self._refresh_checks()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.return',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_refresh_checks(self):
        self._refresh_checks()
        return True

    def action_validate(self):
        for ret in self:
            if ret.state != 'new':
                continue
            ret._refresh_checks()
            pending = ret.check_ids.filtered(lambda c: c.result != 'reviewed')
            if pending:
                raise UserError(_("Review all the checks before validating %(name)s:\n%(checks)s",
                                  name=ret.name, checks='\n'.join('- %s' % c.name for c in pending)))
            if ret.category == 'tax':
                ret._validate_tax_return()
            ret.write({'state': 'reviewed', 'is_completed': ret.states_workflow == 'reviewed'})
        return True

    def _validate_tax_return(self):
        self.ensure_one()
        move_vals = self._prepare_closing_move_vals()
        if move_vals:
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            self.closing_move_id = move
        company = self.company_id.sudo()
        self.previous_tax_lock_date = company.tax_lock_date
        if not company.tax_lock_date or company.tax_lock_date < self.date_to:
            company.tax_lock_date = self.date_to
        self.message_post(body=_(
            "Return validated. Tax due: %(amount)s. Tax lock date set to %(date)s.",
            amount=formatLang(self.env, self.amount_to_pay, currency_obj=self.currency_id),
            date=format_date(self.env, company.tax_lock_date)))

    def action_submit(self):
        for ret in self:
            if ret.state != 'reviewed' or ret.states_workflow == 'reviewed':
                raise UserError(_("Validate %s before submitting it.", ret.name))
            vals = {'state': 'submitted'}
            if ret.states_workflow != 'paid' or ret.category != 'tax' \
                    or ret.currency_id.compare_amounts(ret.amount_to_pay, 0.0) <= 0:
                vals['is_completed'] = True
            ret.write(vals)
        return True

    def action_mark_paid(self):
        for ret in self:
            if ret.state != 'submitted' or ret.states_workflow != 'paid':
                raise UserError(_("Submit %s before marking it as paid.", ret.name))
            ret.write({'state': 'paid', 'is_completed': True})
        return True

    def action_pay(self):
        """ Open a draft payment of the tax due to the payment partner of the return type. """
        self.ensure_one()
        rtype = self.type_id
        if not rtype.payment_partner_id:
            raise UserError(_("Set the Payment Partner of the return type \"%s\" first.", rtype.name))
        if self.currency_id.compare_amounts(self.amount_to_pay, 0.0) <= 0:
            raise UserError(_("There is no tax to pay for %s.", self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pay %s", self.name),
            'res_model': 'account.payment',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {
                'default_payment_type': 'outbound',
                'default_partner_type': 'supplier',
                'default_partner_id': rtype.payment_partner_id.id,
                'default_partner_bank_id': rtype.payment_partner_bank_id.id,
                'default_amount': self.amount_to_pay,
                'default_memo': self.name,
                'default_date': fields.Date.context_today(self),
                'default_company_id': self.company_id.id,
            },
        }

    def action_mark_completed(self):
        self.write({'is_completed': True})
        return True

    def action_mark_uncompleted(self):
        self.write({'is_completed': False})
        return True

    def action_reset(self):
        for ret in self:
            if ret.state == 'new':
                continue
            if ret.closing_move_id:
                move = ret.closing_move_id
                if move.state == 'posted':
                    move.button_draft()
                move.button_cancel()
                ret.closing_move_id = False
            company = ret.company_id.sudo()
            if ret.category == 'tax' and company.tax_lock_date == ret.date_to:
                company.tax_lock_date = ret.previous_tax_lock_date
            ret.write({'state': 'new', 'is_completed': False, 'previous_tax_lock_date': False})
            ret.message_post(body=_("Return reset to draft."))
        return True

    def action_open_closing_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.closing_move_id.id,
            'views': [(False, 'form')],
        }

    def action_open_tax_report(self):
        self.ensure_one()
        return self.env['ir.actions.server']._for_xml_id(
            'hudson_accounting_enhancements.action_server_report_tax')


class AccountReturnCheck(models.Model):
    _name = 'account.return.check'
    _description = "Tax Return Check"
    _order = 'sequence, id'

    return_id = fields.Many2one('account.return', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='return_id.company_id', store=True)
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    message = fields.Text()
    sequence = fields.Integer()
    result = fields.Selection([
        ('todo', 'To Review'),
        ('anomaly', 'Anomaly'),
        ('reviewed', 'Reviewed'),
    ], default='todo', required=True)
    is_automatic = fields.Boolean()
    manually_set = fields.Boolean(help="Reviewed or reset by a user: automatic refreshes keep it.")
    reviewed_by_id = fields.Many2one('res.users', string="Reviewed By")
    notes = fields.Text()
    records_model = fields.Char()
    records_domain = fields.Char()
    records_count = fields.Integer()
    action_xmlid = fields.Char()

    def _get_card_data(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'message': self.message or '',
            'result': self.result,
            'notes': self.notes or '',
            'records_count': self.records_count if self.records_model and self.records_domain else 0,
            'has_action': bool(self.action_xmlid),
            'reviewer_id': self.reviewed_by_id.id or False,
            'reviewer_name': self.reviewed_by_id.name or '',
            'readonly': self.return_id.state != 'new',
        }

    def _check_editable(self):
        if any(check.return_id.state != 'new' for check in self):
            raise UserError(_("The checks of a validated return can't be changed. Reset it first."))

    def action_toggle_review(self):
        self._check_editable()
        for check in self:
            if check.result == 'reviewed':
                check.write({'result': 'todo', 'reviewed_by_id': False, 'manually_set': False})
            else:
                check.write({'result': 'reviewed', 'reviewed_by_id': self.env.user.id,
                             'manually_set': True})
        # An unreviewed automatic check falls back to its computed result.
        self.filtered(lambda c: not c.manually_set and c.is_automatic).return_id._refresh_checks()
        return True

    def action_set_notes(self, notes):
        self.ensure_one()
        self.notes = notes
        return True

    def action_open_records(self):
        self.ensure_one()
        if self.action_xmlid:
            return self.env['ir.actions.actions']._for_xml_id(self.action_xmlid)
        if not (self.records_model and self.records_domain):
            return False
        domain = ast.literal_eval(self.records_domain)
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': self.records_model,
            'domain': domain,
            'views': [(False, 'list'), (False, 'form')],
            'context': {'create': False},
            'target': 'current',
        }
