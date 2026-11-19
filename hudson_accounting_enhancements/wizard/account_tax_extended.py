from collections import defaultdict
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import SQL


class AccountTaxExtendedWizard(models.TransientModel):
    """
    Extended Tax Report with:
    - Breakdown by Tax Group (e.g., Sales Tax, VAT on Purchases)
    - Separate columns for Base Amount and Tax Amount
    - Subtotals per tax type (sale, purchase)
    - Grand total of tax liability
    """
    _name = 'account.tax.extended.wizard'
    _description = 'Extended Tax Report'

    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=lambda self: date.today(),
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
        default=lambda self: self.env.company,
    )

    def _report_company_ids(self):
        """The companies the report covers: the ones selected in the company
        switcher, which always include the wizard's company (checked above)."""
        return (self.env.companies | self.company_id).ids

    def _get_journal_clause(self):
        """Restrict to the journals of the selected Multi Ledgers (passed in context)."""
        journal_ids = self.env.context.get('report_journal_ids')
        if journal_ids:
            return "AND aml.journal_id IN %s", (tuple(journal_ids),)
        return '', ()

    def _get_move_line_domain(self):
        """ The journal items of the period that are due in it: a cash basis tax is reported when it
        is paid (on the cash basis entry), not on the invoice, as in Odoo Enterprise. """
        self.ensure_one()
        states = ('posted',) if self.target_move == 'posted' else ('draft', 'posted')
        MoveLine = self.env['account.move.line']
        domain = Domain([
            # all the companies of the company switcher, as in Odoo
            ('company_id', 'in', self._report_company_ids()),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('parent_state', 'in', states),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]) & MoveLine._get_tax_exigible_domain()
        journal_ids = self.env.context.get('report_journal_ids')
        if journal_ids:
            domain &= Domain('journal_id', 'in', list(journal_ids))
        return domain

    def _compute_tax_data(self):
        """ :return: the taxes of the period by type (sale / purchase) and tax group, as in Odoo
            Enterprise: the sales are positive and their refunds negative (the purchases likewise), so
            that a period with more refunds than sales shows a tax to recover, not a tax to pay. """
        self.ensure_one()
        # company_id can come from client data and is used in raw SQL
        if self.company_id not in self.env.companies:
            raise UserError(_("You are not allowed to access this company's data."))
        if self.date_from > self.date_to:
            raise UserError(_('The start date must be on or before the end date.'))
        df = self.date_from
        dt = self.date_to
        state = self.target_move
        Tax = self.env['account.tax'].with_context(active_test=False)

        line_ids = self.env['account.move.line']._search(self._get_move_line_domain()).subselect()
        # tax amounts, by tax of the tax lines
        self.env.cr.execute(SQL("""
            SELECT aml.tax_line_id, SUM(aml.balance)
              FROM account_move_line aml
             WHERE aml.id IN %s AND aml.tax_line_id IS NOT NULL
          GROUP BY aml.tax_line_id
        """, line_ids))
        tax_by_tax = dict(self.env.cr.fetchall())
        # base amounts, by tax of the base lines (0% and exempt taxes only have these)
        self.env.cr.execute(SQL("""
            SELECT rel.account_tax_id, SUM(aml.balance)
              FROM account_move_line aml
              JOIN account_move_line_account_tax_rel rel ON rel.account_move_line_id = aml.id
             WHERE aml.id IN %s
          GROUP BY rel.account_tax_id
        """, line_ids))
        base_by_tax = defaultdict(float)
        for tax_id, base in self.env.cr.fetchall():
            tax = Tax.browse(tax_id)
            # the base lines carry the group: its base is the base of each of its taxes
            for target in (tax.children_tax_ids if tax.amount_type == 'group' else tax):
                base_by_tax[target.id] += base or 0.0

        groups = {}
        currency = self.company_id.currency_id
        for tax in Tax.browse(list(set(tax_by_tax) | set(base_by_tax))).sorted(lambda t: (t.sequence, t.name or '')):
            if tax.amount_type == 'group':
                continue
            tax_type = tax.type_tax_use
            if tax_type not in ('sale', 'purchase'):
                # a tax of a group takes the use of its group
                parent = Tax.search([('children_tax_ids', 'in', tax.ids)], limit=1)
                tax_type = parent.type_tax_use
            if tax_type not in ('sale', 'purchase'):
                continue
            # sales are credits: shown positive, their refunds negative; purchases are debits
            sign = -1.0 if tax_type == 'sale' else 1.0
            tax_amount = sign * (tax_by_tax.get(tax.id) or 0.0)
            base_amount = sign * base_by_tax.get(tax.id, 0.0)
            if currency.is_zero(tax_amount) and currency.is_zero(base_amount):
                continue
            group_name = tax.tax_group_id.name or _('Ungrouped')
            key = (tax_type, group_name)
            if key not in groups:
                groups[key] = {
                    'type': tax_type,
                    'type_label': _('Sales Tax') if tax_type == 'sale' else _('Purchase Tax'),
                    'group_name': group_name,
                    'taxes': [],
                    'total_base': 0.0,
                    'total_tax': 0.0,
                }
            groups[key]['taxes'].append({
                'tax_id': tax.id,
                'name': tax.name or _('Unnamed Tax'),
                'rate': tax.amount,
                'base_amount': base_amount,
                'tax_amount': tax_amount,
            })
            groups[key]['total_base'] += base_amount
            groups[key]['total_tax'] += tax_amount

        ordered = sorted(groups.values(), key=lambda g: g['group_name'])
        sale_groups = [g for g in ordered if g['type'] == 'sale']
        purchase_groups = [g for g in ordered if g['type'] == 'purchase']

        total_sale_tax = sum(g['total_tax'] for g in sale_groups)
        total_purchase_tax = sum(g['total_tax'] for g in purchase_groups)
        # positive: tax to pay; negative: tax to recover
        net_tax = total_sale_tax - total_purchase_tax

        return {
            'date_from': df,
            'date_to': dt,
            'company': self.company_id.id,
            'target_move': state,
            'sale_groups': sale_groups,
            'purchase_groups': purchase_groups,
            'total_sale_tax': total_sale_tax,
            'total_purchase_tax': total_purchase_tax,
            'net_tax': net_tax,
        }

    def action_print_report(self):
        self.ensure_one()
        data = self._compute_tax_data()
        return self.env.ref(
            'hudson_accounting_enhancements.action_report_tax_extended'
        ).report_action(self, data={'form': data})

    def check_report(self):
        return self.action_print_report()
