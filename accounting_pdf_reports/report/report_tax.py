from odoo import api, models, _
from odoo.exceptions import UserError


class ReportTax(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_tax'
    _description = 'Tax Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()
        return {
            'data': data['form'],
            'lines': self.get_lines(data.get('form')),
        }

    def _sql_from_amls_one(self):
        sql = ("""SELECT "account_move_line".tax_line_id, """
               """COALESCE(SUM("account_move_line".debit-"account_move_line".credit), 0)
                    FROM %s
                    WHERE %s GROUP BY "account_move_line".tax_line_id""")
        return sql

    def _sql_from_amls_two(self):
        sql = """SELECT r.account_tax_id, COALESCE(SUM("account_move_line".debit-"account_move_line".credit), 0)
                 FROM %s
                 INNER JOIN account_move_line_account_tax_rel r ON ("account_move_line".id = r.account_move_line_id)
                 INNER JOIN account_tax t ON (r.account_tax_id = t.id)
                 WHERE %s GROUP BY r.account_tax_id"""
        return sql

    def _compute_from_amls(self, options, taxes):
        """ Fill the tax and base amounts of `taxes` ({tax_id: values}) with the balance of the journal
        items, debit positive. Only the items due in the period count: a cash basis tax is reported
        on the cash basis entry of its payment, not on the invoice (as in Odoo Enterprise). """
        MoveLine = self.env['account.move.line']
        exigible_domain = list(MoveLine._get_tax_exigible_domain())
        #compute the tax amount
        sql = self._sql_from_amls_one()
        tables, where_clause, where_params = MoveLine._query_get(list(exigible_domain))
        query = sql % (tables, where_clause)
        self.env.cr.execute(query, where_params)
        results = self.env.cr.fetchall()
        for result in results:
            if result[0] in taxes:
                taxes[result[0]]['tax'] += result[1] or 0.0

        #compute the net amount
        sql2 = self._sql_from_amls_two()
        tables, where_clause, where_params = MoveLine._query_get(list(exigible_domain))
        query = sql2 % (tables, where_clause)
        self.env.cr.execute(query, where_params)
        results = self.env.cr.fetchall()
        for tax_id, base in results:
            # the base of a group of taxes is on the group: it is the base of each tax of the group
            for target_id in options.get('_base_targets', {}).get(tax_id, [tax_id]):
                if target_id in taxes:
                    taxes[target_id]['net'] += base or 0.0

    @api.model
    def get_lines(self, options):
        """ :return: {'sale': [tax values], 'purchase': [tax values]} where the base ('net') and the tax are
            positive for the sales and the purchases of the period and negative for their refunds,
            as in Odoo Enterprise. """
        taxes = {}
        base_targets = {}
        # archived taxes still have entries in the past periods
        all_taxes = self.env['account.tax'].with_context(active_test=False).search([('type_tax_use', '!=', 'none')])
        for tax in all_taxes:
            if tax.amount_type == 'group' and tax.children_tax_ids:
                base_targets[tax.id] = tax.children_tax_ids.ids
                for child in tax.children_tax_ids:
                    if child.type_tax_use != 'none':
                        # a child usable on its own is reported as itself, below
                        continue
                    taxes[child.id] = {'tax': 0, 'net': 0, 'name': child.name, 'type': tax.type_tax_use}
            else:
                taxes[tax.id] = {'tax': 0, 'net': 0, 'name': tax.name, 'type': tax.type_tax_use}
        # used_context carries company_id and journal_ids as well; building a fresh
        # context here would make the report span every company of the switcher.
        report_context = dict(options.get('used_context') or {})
        report_context.update(
            date_from=options['date_from'],
            date_to=options['date_to'],
            state=options['target_move'],
            strict_range=True,
        )
        self.with_context(**report_context)._compute_from_amls(dict(options, _base_targets=base_targets), taxes)
        groups = dict((tp, []) for tp in ['sale', 'purchase'])
        for tax in taxes.values():
            if tax['type'] not in groups:
                continue
            # a sale is a credit: print it positive, its refunds negative (debit balances stay
            # positive for the purchases)
            if tax['type'] == 'sale':
                tax['tax'] = -tax['tax']
                tax['net'] = -tax['net']
            # keep 0%-rated taxes: they have no tax amount but a real base amount
            if tax['tax'] or tax['net']:
                groups[tax['type']].append(tax)
        return groups
