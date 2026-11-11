from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HudsonLoan(models.Model):
    _name = 'hudson.loan'
    _description = 'Loan Management'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char(string='Name', required=True, tracking=True)
    amount_borrowed = fields.Monetary(string='Amount Borrowed', required=True, tracking=True)
    interest = fields.Monetary(string='Interest', compute='_compute_totals', store=True)
    outstanding_balance = fields.Monetary(string='Outstanding Balance', compute='_compute_totals', store=True)
    
    date = fields.Date(string='Loan Date', required=True, default=fields.Date.context_today)
    duration = fields.Integer(string='Duration (months)', required=True, default=12)
    asset_group = fields.Char(string='Asset Group')
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            if self.long_term_account_id and self.company_id not in self.long_term_account_id.company_ids:
                self.long_term_account_id = False
            if self.short_term_account_id and self.company_id not in self.short_term_account_id.company_ids:
                self.short_term_account_id = False
            if self.expense_account_id and self.company_id not in self.expense_account_id.company_ids:
                self.expense_account_id = False
            if self.journal_id and self.journal_id.company_id != self.company_id:
                self.journal_id = False
            if self.disbursement_account_id and self.company_id not in self.disbursement_account_id.company_ids:
                self.disbursement_account_id = False
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # Amortization Schedule
    line_ids = fields.One2many('hudson.loan.line', 'loan_id', string='Amortization Schedule')
    
    # Loan Settings
    long_term_account_id = fields.Many2one(
        'account.account',
        string='Long Term Account',
        required=True,
        check_company=True,
    )
    short_term_account_id = fields.Many2one(
        'account.account',
        string='Short Term Account',
        required=True,
        check_company=True,
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        required=True,
        check_company=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        check_company=True,
    )
    skip_until_date = fields.Date(
        string='Skip until',
        help="Upon confirmation of the loan, Odoo will ignore the loan lines that are up to this date (included) and not create entries for them. This is useful if you have already manually created entries prior to the creation of this loan."
    )
    receive_disbursement = fields.Boolean(string='Create Disbursement Entry', default=False)
    disbursement_account_id = fields.Many2one(
        'account.account',
        string='Disbursement Account (Bank)',
        check_company=True,
    )
    
    # Posted Entries
    move_ids = fields.One2many('account.move', 'hudson_loan_id', string='Loan Entries')
    move_count = fields.Integer(compute='_compute_move_count')

    @api.depends('line_ids.principal', 'line_ids.interest', 'line_ids.balance', 'line_ids.is_posted')
    def _compute_totals(self):
        for loan in self:
            loan.interest = sum(loan.line_ids.mapped('interest'))
            if loan.line_ids:
                # Outstanding balance is the amount borrowed minus the sum of posted/skipped principal payments
                posted_principal = sum(loan.line_ids.filtered(lambda l: l.is_posted).mapped('principal'))
                loan.outstanding_balance = loan.amount_borrowed - posted_principal
            else:
                loan.outstanding_balance = loan.amount_borrowed

    @api.depends('move_ids')
    def _compute_move_count(self):
        for loan in self:
            loan.move_count = len(loan.move_ids)
            
    @api.depends('name', 'date', 'duration', 'line_ids.date')
    def _compute_display_name(self):
        for loan in self:
            if loan.line_ids:
                dates = [d for d in loan.line_ids.mapped('date') if d]
                if dates:
                    min_date = min(dates)
                    max_date = max(dates)
                    loan.display_name = f"{loan.name}: {min_date.strftime('%m %Y')} - {max_date.strftime('%m %Y')}"
                    continue
            if loan.date and loan.duration:
                from dateutil.relativedelta import relativedelta
                start = loan.date
                end = start + relativedelta(months=max(0, loan.duration - 1))
                loan.display_name = f"{loan.name}: {start.strftime('%m %Y')} - {end.strftime('%m %Y')}"
            else:
                loan.display_name = loan.name or _('New Loan')

    def action_compute(self):
        self.ensure_one()
        return {
            'name': _('Compute New Loan'),
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.loan.compute.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loan_id': self.id,
                'default_company_id': self.company_id.id,
                'default_amount': self.amount_borrowed,
                'default_start_date': self.date or fields.Date.context_today(self),
                'default_term_years': max(1, self.duration // 12) if self.duration else 1,
            }
        }

    def action_confirm(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only draft loans can be confirmed."))
        if not self.long_term_account_id or not self.short_term_account_id or not self.expense_account_id or not self.journal_id:
            raise UserError(_("Please configure the Loan Settings accounts and Journal before confirming."))
            
        if not self.line_ids:
            raise UserError(_("Please compute the amortization schedule before confirming."))

        # Delete any existing draft moves linked to this loan before generating
        existing_draft_moves = self.move_ids.filtered(lambda m: m.state == 'draft')
        existing_draft_moves.unlink()

        currency = self.currency_id or self.company_id.currency_id
        today = fields.Date.context_today(self)
        Move = self.env['account.move'].with_company(self.company_id)

        # Handle optional initial disbursement
        if self.receive_disbursement and self.disbursement_account_id:
            disb_move_vals = {
                'date': self.date,
                'journal_id': self.journal_id.id,
                'company_id': self.company_id.id,
                'hudson_loan_id': self.id,
                'ref': f"{self.name} - Loan Disbursement",
                'auto_post': 'at_date',
                'line_ids': [
                    (0, 0, {
                        'name': 'Loan Disbursement Received',
                        'account_id': self.disbursement_account_id.id,
                        'debit': currency.round(self.amount_borrowed),
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': 'Long-term Borrowing',
                        'account_id': self.long_term_account_id.id,
                        'debit': 0.0,
                        'credit': currency.round(self.amount_borrowed),
                    }),
                ]
            }
            disb_move = Move.create(disb_move_vals)
            if disb_move.date <= today:
                disb_move.action_post()

        sorted_lines = self.line_ids.sorted('date')
        prev_reclass_info = None

        for idx, line in enumerate(sorted_lines):
            if self.skip_until_date and line.date <= self.skip_until_date:
                continue

            line_principal = currency.round(line.principal)
            line_interest = currency.round(line.interest)
            line_payment = currency.round(line.principal + line.interest)

            # 1. Principal & Interest Payment Entry
            payment_vals = {
                'date': line.date,
                'journal_id': self.journal_id.id,
                'company_id': self.company_id.id,
                'hudson_loan_id': self.id,
                'ref': f"{self.name} - Principal & Interest {line.date.strftime('%m/%Y')}",
                'auto_post': 'at_date',
                'line_ids': [
                    (0, 0, {
                        'name': 'Principal Repayment',
                        'account_id': self.long_term_account_id.id,
                        'debit': line_principal,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': 'Interest Expense',
                        'account_id': self.expense_account_id.id,
                        'debit': line_interest,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': 'Bank/Liability',
                        'account_id': self.short_term_account_id.id,
                        'debit': 0.0,
                        'credit': line_payment,
                    }),
                ]
            }
            payment_move = Move.create(payment_vals)
            line.move_id = payment_move.id
            if payment_move.date <= today:
                payment_move.action_post()

            # 2. Reclassification LT - ST for upcoming 12 months (if future lines exist)
            future_lines = sorted_lines[idx + 1 : idx + 1 + 12]
            current_reclass_info = None
            if future_lines:
                start_str = future_lines[0].date.strftime('%m/%Y')
                end_str = future_lines[-1].date.strftime('%m/%Y')
                reclass_amount = currency.round(sum(fl.principal for fl in future_lines))
                current_reclass_info = (start_str, end_str, reclass_amount)

                reclass_vals = {
                    'date': line.date,
                    'journal_id': self.journal_id.id,
                    'company_id': self.company_id.id,
                    'hudson_loan_id': self.id,
                    'ref': f"{self.name} - Reclassification LT - ST {start_str} to {end_str}",
                    'auto_post': 'at_date',
                    'line_ids': [
                        (0, 0, {
                            'name': 'Long-term debt reclassification',
                            'account_id': self.long_term_account_id.id,
                            'debit': reclass_amount,
                            'credit': 0.0,
                        }),
                        (0, 0, {
                            'name': 'Short-term debt reclassification',
                            'account_id': self.short_term_account_id.id,
                            'debit': 0.0,
                            'credit': reclass_amount,
                        }),
                    ]
                }
                reclass_move = Move.create(reclass_vals)
                if reclass_move.date <= today:
                    reclass_move.action_post()

            # 3. Reversal of Previous Period's Reclassification LT - ST (from period 2 onwards)
            if prev_reclass_info:
                prev_start, prev_end, prev_amt = prev_reclass_info
                reversal_vals = {
                    'date': line.date,
                    'journal_id': self.journal_id.id,
                    'company_id': self.company_id.id,
                    'hudson_loan_id': self.id,
                    'ref': f"{self.name} - Reversal reclassification LT - ST {prev_start} to {prev_end}",
                    'auto_post': 'at_date',
                    'line_ids': [
                        (0, 0, {
                            'name': 'Reversal short-term debt reclassification',
                            'account_id': self.short_term_account_id.id,
                            'debit': prev_amt,
                            'credit': 0.0,
                        }),
                        (0, 0, {
                            'name': 'Reversal long-term debt reclassification',
                            'account_id': self.long_term_account_id.id,
                            'debit': 0.0,
                            'credit': prev_amt,
                        }),
                    ]
                }
                reversal_move = Move.create(reversal_vals)
                if reversal_move.date <= today:
                    reversal_move.action_post()

            # Advance previous reclassification info
            prev_reclass_info = current_reclass_info

        self.state = 'running'

    def action_cancel(self):
        for loan in self:
            # Failures (lock date, hashed entries) must stop the cancellation: a
            # cancelled loan must not leave posted entries behind.
            for move in loan.move_ids:
                if move.state == 'posted':
                    move.button_draft()
                try:
                    with self.env.cr.savepoint():
                        move.unlink()
                except UserError:
                    # e.g. part of a sequence chain: keep it, cancelled
                    move.button_cancel()
            loan.state = 'cancelled'

    def action_reset_to_draft(self):
        for loan in self:
            posted_moves = loan.move_ids.filtered(lambda m: m.state == 'posted')
            if posted_moves:
                for move in posted_moves:
                    try:
                        move.button_draft()
                    except Exception as e:
                        raise UserError(_("Cannot reset to draft while posted entry %s cannot be drafted: %s", move.name, str(e)))
            loan.move_ids.unlink()
            loan.state = 'draft'


    def action_close(self):
        for loan in self:
            loan.state = 'closed'

    def action_view_entries(self):
        self.ensure_one()
        list_view = self.env.ref('hudson_accounting_enhancements.view_account_move_loan_entries_tree', raise_if_not_found=False)
        form_view = self.env.ref('account.view_move_form', raise_if_not_found=False)
        search_view = self.env.ref('account.view_account_move_filter', raise_if_not_found=False)
        views = []
        if list_view:
            views.append((list_view.id, 'list'))
        if form_view:
            views.append((form_view.id, 'form'))
        if not views:
            views = [(False, 'list'), (False, 'form')]
        action = {
            'name': _('Loan Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': views,
            'domain': [('hudson_loan_id', '=', self.id)],
            'context': dict(self.env.context, default_hudson_loan_id=self.id, default_move_type='entry'),
        }
        if search_view:
            action['search_view_id'] = [search_view.id, 'search']
        return action

class HudsonLoanLine(models.Model):
    _name = 'hudson.loan.line'
    _description = 'Loan Amortization Line'
    _order = 'date asc'
    _check_company_auto = True

    loan_id = fields.Many2one('hudson.loan', string='Loan', ondelete='cascade', index=True, required=True, check_company=True)
    date = fields.Date(string='Date', required=True, index=True)
    principal = fields.Monetary(string='Principal', currency_field='currency_id')
    interest = fields.Monetary(string='Interest', currency_field='currency_id')
    payment = fields.Monetary(string='Payment', currency_field='currency_id')
    balance = fields.Monetary(string='Outstanding Balance', currency_field='currency_id')
    
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, check_company=True)
    is_posted = fields.Boolean(string='Posted', compute='_compute_is_posted', store=True)
    
    loan_state = fields.Selection(related='loan_id.state', string='Status', store=True)
    company_id = fields.Many2one('res.company', related='loan_id.company_id', string='Company', store=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', related='loan_id.currency_id', store=True, readonly=True)
    asset_group = fields.Char(related='loan_id.asset_group', string='Asset Group', store=True)

    @api.depends('move_id.state', 'loan_id.skip_until_date', 'loan_id.state', 'date')
    def _compute_is_posted(self):
        for line in self:
            if line.move_id and line.move_id.state == 'posted':
                line.is_posted = True
            elif line.loan_id.skip_until_date and line.date and line.date <= line.loan_id.skip_until_date and line.loan_id.state in ('running', 'closed'):
                line.is_posted = True
            else:
                line.is_posted = False

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    hudson_loan_id = fields.Many2one('hudson.loan', string='Loan Reference')
