# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Employee deductions (salary rule codes) -> payroll account key of the company
DEDUCTION_ACCOUNTS = [
    ({'HDS_IN_TDS', 'TDS', 'INCOME_TAX', 'IT'}, 'tds'),
    ({'EPF', 'PF', 'EE_PF'}, 'pf_employee'),
    ({'ESIC_EE', 'EE_ESI'}, 'esic_employee'),
    ({'PT', 'PROF_TAX'}, 'pt'),
    ({'LWF_EE', 'EE_LWF', 'LWF'}, 'lwf_employee'),
]
# Deductions that reduce the salary expense instead of being owed to someone (unpaid leave)
CONTRA_EXPENSE_CODES = {'UNPAID'}
# Employer statutory contributions (payslip fields, Indian payroll) -> payable account key, label
EMPLOYER_CONTRIBUTIONS = [
    (('hds_in_employer_epf',), 'pf_employer', 'Provident Fund - Employer'),
    (('hds_in_employer_edli', 'hds_in_employer_epf_admin'), 'pf_admin', 'EPF Admin & EDLI'),
    (('hds_in_employer_esic',), 'esic_employer', "Employer's State Insurance Corporation"),
    (('hds_in_employer_lwf',), 'lwf_employer', 'Labour Welfare Fund - Employer'),
]


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    date = fields.Date(
        string='Accounting Date',
        help="Keep empty to use the payslip payment date."
    )

    @api.model
    def _default_journal_id(self):
        company = self.env.company
        journal = self.env['account.journal'].search([
            ('company_id', '=', company.id),
            ('type', '=', 'general'),
            '|', ('code', '=', 'SAL'), ('name', 'ilike', 'Salar'),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].search([
                ('company_id', '=', company.id),
                '|', ('code', '=', 'SAL'), ('name', 'ilike', 'Salar'),
            ], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': 'Salaries',
                'code': 'SAL',
                'type': 'general',
                'company_id': company.id,
                'sequence': 10,
            })
        return journal

    journal_id = fields.Many2one(
        'account.journal',
        string='Salary Journal',
        required=True,
        default=lambda self: self._default_journal_id(),
        domain="[('company_id', '=', company_id)]",
        help="Select Salary Journal for accounting entries."
    )
    journal_name = fields.Char(
        string='Salary Journal',
        compute='_compute_journal_name'
    )
    move_id = fields.Many2one(
        'account.move',
        string='Accounting Entry',
        readonly=True,
        copy=False,
        help="Accounting entry generated for this payslip."
    )
    move_state = fields.Selection(related='move_id.state', string='Journal Entry Status')

    @api.depends('journal_id', 'journal_id.name')
    def _compute_journal_name(self):
        for slip in self:
            slip.journal_name = slip.journal_id.name if slip.journal_id else 'Salaries'

    def action_open_salary_journal_entries(self):
        """Opens the related Journal Entry (if exists) or the Journal Entries list of Salary Journal."""
        self.ensure_one()
        if self.move_id:
            return {
                'name': _('Accounting Entry'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': self.move_id.id,
                'target': 'current',
            }
        journal = self.journal_id or self._default_journal_id()
        return {
            'name': _('Journal Entries: %s') % journal.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(self.env.ref('hudson_payroll_account.view_move_tree_payroll').id, 'list'),
                      (self.env.ref('account.view_move_form').id, 'form')],
            'search_view_id': [self.env.ref('account.view_account_move_filter').id],
            'domain': [('journal_id', '=', journal.id)],
            'context': {
                'default_journal_id': journal.id,
                'search_default_journal_id': journal.id,
            },
            'target': 'current',
        }

    @api.onchange('company_id')
    def _onchange_company_id_salary_journal(self):
        if self.company_id:
            journal = self.env['account.journal'].search([
                ('company_id', '=', self.company_id.id),
                ('type', '=', 'general'),
                '|', ('code', '=', 'SAL'), ('name', 'ilike', 'Salar'),
            ], limit=1)
            if not journal:
                journal = self.env['account.journal'].sudo().create({
                    'name': 'Salaries',
                    'code': 'SAL',
                    'type': 'general',
                    'company_id': self.company_id.id,
                    'sequence': 10,
                })
            self.journal_id = journal

    @api.model_create_multi
    def create(self, vals_list):
        journal_id = self.env.context.get('journal_id')
        if journal_id:
            for vals in vals_list:
                if 'journal_id' not in vals:
                    vals['journal_id'] = journal_id
        return super().create(vals_list)

    def write(self, vals):
        res = super(HrPayslip, self).write(vals)
        # When moving to paid or done status, ensure entry is generated in draft status
        if vals.get('state') in ('done', 'paid') or vals.get('paid'):
            self.filtered(lambda slip: not slip.move_id)._create_account_move()
        return res

    @api.onchange('contract_id')
    def onchange_contract_id(self):
        if hasattr(super(), 'onchange_contract_id'):
            super().onchange_contract_id()
        if self.contract_id and hasattr(self.contract_id, 'journal_id') and self.contract_id.journal_id:
            self.journal_id = self.contract_id.journal_id

    def action_payslip_cancel(self):
        """Cancel the payslip: its draft journal entry is deleted, a posted one is reversed."""
        self._hds_release_account_move()
        return super(HrPayslip, self).action_payslip_cancel()

    def unlink(self):
        self._hds_release_account_move()
        return super().unlink()

    def action_payslip_done(self):
        """Finalize the payslip and create draft journal entry."""
        res = super(HrPayslip, self).action_payslip_done()
        self._create_account_move()
        return res

    def action_payslip_paid(self):
        """Mark payslip as paid and generate draft journal entry."""
        res = super(HrPayslip, self).action_payslip_paid()
        self.filtered(lambda slip: not slip.move_id)._create_account_move()
        return res

    def action_post_account_move(self):
        """Allows posting the draft accounting entry directly."""
        self.ensure_one()
        if not self.move_id and self.state in ('done', 'paid'):
            self._create_account_move()
        if self.move_id and self.move_id.state == 'draft':
            self.move_id.action_post()
        return True

    # ------------------------------------------------------------------
    # Journal entry of the payslip
    # ------------------------------------------------------------------
    def _hds_account_override(self, account):
        """A salary rule's own account, when it belongs to the payslip's company."""
        self.ensure_one()
        return account if account and self.company_id in account.company_ids else False

    def _hds_payroll_move_lines(self, accounts):
        """(account, label, debit, credit, partner, analytic) of the payslip's journal entry:
        Dr salary expense (gross) and employer contribution expense; Cr each employee deduction's
        payable, each employer contribution's payable and the net salary payable (employee)."""
        self.ensure_one()
        currency = self.company_id.currency_id
        lines = []
        employee_partner = (self.employee_id.work_contact_id or self.employee_id.user_id.partner_id)
        analytic = False
        if self.contract_id and getattr(self.contract_id, 'analytic_account_id', False):
            analytic = {str(self.contract_id.analytic_account_id.id): 100}

        def amount(value):
            return currency.round(abs(value or 0.0))

        def add(account, label, debit=0.0, credit=0.0, partner=False, analytic_distribution=False):
            if account and not (currency.is_zero(debit) and currency.is_zero(credit)):
                lines.append((account, label, debit, credit, partner, analytic_distribution))

        slip_lines = self.line_ids.filtered(lambda line: not currency.is_zero(line.total))

        # Gross salary (all earnings) -> salary expense
        gross_lines = slip_lines.filtered(lambda line: (line.code or '').upper() == 'GROSS')
        gross = amount(sum(gross_lines.mapped('total'))) if gross_lines else amount(self.gross_wage)
        gross_rule = gross_lines[:1].salary_rule_id
        add(self._hds_account_override(gross_rule.account_debit_id) or accounts['salary_expense'],
            _('Gross Salary'), debit=gross, analytic_distribution=analytic)

        # Employee deductions -> their payable (unpaid leave reduces the salary expense)
        for line in slip_lines.filtered(lambda l: l.salary_rule_id.category_id.code == 'DED'):
            code = (line.code or '').upper()
            if code in CONTRA_EXPENSE_CODES:
                account = accounts['salary_expense']
            else:
                key = next((k for codes, k in DEDUCTION_ACCOUNTS if code in codes), 'other_deductions')
                account = self._hds_account_override(line.salary_rule_id.account_credit_id) or accounts[key]
            add(account, line.name, credit=amount(line.total))

        # Employer statutory contributions -> employer expense / their payable
        employer_total = 0.0
        for field_names, key, label in EMPLOYER_CONTRIBUTIONS:
            value = amount(sum(getattr(self, name, 0.0) or 0.0 for name in field_names if name in self._fields))
            if not currency.is_zero(value):
                employer_total += value
                add(accounts[key], label, credit=value)
        add(accounts['employer_expense'], _('Employer Statutory Contributions'),
            debit=currency.round(employer_total), analytic_distribution=analytic)

        # Net salary -> salary payable to the employee
        net_lines = slip_lines.filtered(lambda line: (line.code or '').upper() == 'NET')
        net = amount(sum(net_lines.mapped('total'))) if net_lines else amount(self.net_wage)
        net_rule = net_lines[:1].salary_rule_id
        add(self._hds_account_override(net_rule.account_credit_id) or accounts['net_payable'],
            _('Net Salary'), credit=net, partner=employee_partner.id if employee_partner else False)

        # Earnings outside the gross (e.g. reimbursements after it) or deductions outside DED keep
        # the entry balanced on the salary expense / other deductions payable
        difference = currency.round(sum(l[3] for l in lines) - sum(l[2] for l in lines))
        if difference > 0:
            add(accounts['salary_expense'], _('Other Earnings'), debit=difference, analytic_distribution=analytic)
        elif difference < 0:
            add(accounts['other_deductions'], _('Other Deductions'), credit=-difference)
        return lines

    def _hds_move_line_values(self, accounts, label_employee=False):
        """Journal items (create commands) of the payslip, linked to it."""
        self.ensure_one()
        refund = bool(self.credit_note)
        commands = []
        for account, label, debit, credit, partner, analytic in self._hds_payroll_move_lines(accounts):
            vals = {
                'name': f'{self.employee_id.name} - {label}' if label_employee else label,
                'account_id': account.id,
                'partner_id': partner,
                'debit': credit if refund else debit,
                'credit': debit if refund else credit,
                'hds_payslip_id': self.id,
            }
            if analytic:
                vals['analytic_distribution'] = analytic
            commands.append((0, 0, vals))
        return commands

    def _hds_uses_batch_entry(self):
        """Payslip of a pay run whose company makes one consolidated entry per pay run."""
        self.ensure_one()
        return bool(self.payslip_run_id) and bool(getattr(self.company_id, 'payrun_accounting', False))

    def _create_account_move(self):
        """Create the draft journal entry of validated / paid payslips, in the company's Salary
        Journal, with the company's payroll accounts (Payroll Settings): one entry per payslip, or
        one entry per pay run when Batch Accounting Entries is enabled."""
        slips = self.filtered(lambda slip: not slip.move_id and slip.state in ('done', 'paid'))
        ready = self.browse()
        for slip in slips:
            company = slip.company_id or self.env.company
            if company._hds_has_chart_of_accounts():
                ready |= slip
            else:
                slip.message_post(body=_(
                    "No journal entry was created: %s has no chart of accounts. Set it up in "
                    "Settings > Invoicing > Fiscal Localization.", company.name))
        batch = ready.filtered(lambda slip: slip._hds_uses_batch_entry())
        for slip in ready - batch:
            company = slip.company_id or self.env.company
            accounts = company._hds_get_payroll_accounts()
            journal = slip._hds_salary_journal()
            date_entry = slip.date or slip.date_to or fields.Date.context_today(slip)
            line_vals = slip._hds_move_line_values(accounts)
            if not line_vals:
                continue
            # Created as superuser: payroll users validate payslips without accounting rights
            move = self.env['account.move'].sudo().with_company(company).create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': date_entry,
                'ref': slip.number or slip.name,
                'narration': _('Payslip of %(employee)s (%(start)s - %(end)s)', employee=slip.employee_id.name,
                               start=slip.date_from, end=slip.date_to),
                'line_ids': line_vals,
            })
            slip.write({'move_id': move.id, 'date': date_entry, 'journal_id': journal.id})
        for run in batch.payslip_run_id:
            run_slips = batch.filtered(lambda slip: slip.payslip_run_id == run)
            company = run_slips[0].company_id or self.env.company
            accounts = company._hds_get_payroll_accounts()
            journal = run_slips[0]._hds_salary_journal()
            date_entry = run_slips[0].date or run.date_end or run_slips[0].date_to or fields.Date.context_today(run)
            line_vals = []
            for slip in run_slips:
                line_vals += slip._hds_move_line_values(accounts, label_employee=True)
            if not line_vals:
                continue
            # The pay run's draft entry receives the newly validated payslips
            move = (run.slip_ids - run_slips).move_id.filtered(
                lambda m: m.state == 'draft' and m.journal_id == journal and m.date == date_entry)[:1].sudo()
            if move:
                move.write({'line_ids': line_vals})
            else:
                move = self.env['account.move'].sudo().with_company(company).create({
                    'move_type': 'entry',
                    'journal_id': journal.id,
                    'date': date_entry,
                    'ref': run.name,
                    'narration': _('Pay run %(run)s (%(start)s - %(end)s)', run=run.name,
                                   start=run.date_start, end=run.date_end),
                    'line_ids': line_vals,
                })
            run_slips.write({'move_id': move.id, 'date': date_entry, 'journal_id': journal.id})
        return True

    def _hds_salary_journal(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        return self.journal_id if self.journal_id.company_id == company else \
            self.with_company(company)._default_journal_id()

    def _hds_release_account_move(self):
        """Cancelled / deleted payslip: its draft journal entry is deleted and a posted one is
        reversed. In a pay run's consolidated entry, only the payslip's own journal items are removed
        (draft) or reversed (posted)."""
        for slip in self.filtered('move_id'):
            move = slip.move_id.sudo()
            own_lines = move.line_ids.filtered(lambda line: line.hds_payslip_id == slip)
            shared = bool(own_lines) and bool(move.line_ids - own_lines)
            if not shared:
                if move.state == 'posted':
                    reversal = move._reverse_moves([{
                        'date': fields.Date.context_today(slip),
                        'ref': _('Reversal of %(entry)s (payslip %(slip)s cancelled)', entry=move.name,
                                 slip=slip.number or slip.name),
                    }], cancel=True)
                    slip.message_post(body=_("Journal entry %(entry)s reversed by %(reversal)s.",
                                             entry=move.name, reversal=reversal.name))
                elif move.state == 'draft':
                    move.unlink()
            elif move.state == 'draft':
                own_lines.with_context(dynamic_unlink=True).unlink()
            elif move.state == 'posted':
                reversal = self.env['account.move'].sudo().with_company(move.company_id).create({
                    'move_type': 'entry',
                    'journal_id': move.journal_id.id,
                    'date': fields.Date.context_today(slip),
                    'ref': _('Reversal of %(slip)s in %(entry)s (payslip cancelled)', slip=slip.number or slip.name,
                             entry=move.name),
                    'line_ids': [(0, 0, {
                        'name': line.name,
                        'account_id': line.account_id.id,
                        'partner_id': line.partner_id.id,
                        'debit': line.credit,
                        'credit': line.debit,
                        'analytic_distribution': line.analytic_distribution,
                        'hds_payslip_id': slip.id,
                    }) for line in own_lines],
                })
                reversal.action_post()
                slip.message_post(body=_("Payslip amounts of journal entry %(entry)s reversed by %(reversal)s.",
                                         entry=move.name, reversal=reversal.name))
            slip.move_id = False

    def action_open_account_move(self):
        """Opens the related Accounting Entry for this payslip."""
        self.ensure_one()
        if not self.move_id:
            if self.state in ('done', 'paid'):
                self._create_account_move()
        if not self.move_id:
            return False
        return {
            'name': _('Accounting Entry'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'current',
        }
