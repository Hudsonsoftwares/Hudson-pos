from datetime import date
from odoo import api, fields, models, _
from odoo.exceptions import UserError


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

    def _get_journal_clause(self):
        """Restrict to the journals of the selected Multi Ledgers (passed in context)."""
        journal_ids = self.env.context.get('report_journal_ids')
        if journal_ids:
            return "AND aml.journal_id IN %s", (tuple(journal_ids),)
        return '', ()

    def _compute_tax_data(self):
        self.ensure_one()
        # company_id can come from client data and is used in raw SQL
        if self.company_id not in self.env.companies:
            raise UserError(_("You are not allowed to access this company's data."))
        company_id = self.company_id.id
        df = self.date_from
        dt = self.date_to
        state = self.target_move

        state_clause = "AND am.state = 'posted'" if state == 'posted' else "AND am.state IN ('draft', 'posted')"
        journal_clause, journal_params = self._get_journal_clause()

        # Query 1: Tax amounts per tax (from tax account lines)
        query_tax = f"""
            SELECT
                at.id AS tax_id,
                at.name AS tax_name,
                at.type_tax_use AS tax_type,
                atg.name AS tax_group_name,
                at.amount AS tax_rate,
                COALESCE(SUM(aml.debit - aml.credit), 0.0) AS tax_amount
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_tax at ON at.id = aml.tax_line_id
            LEFT JOIN account_tax_group atg ON atg.id = at.tax_group_id
            WHERE aml.company_id = %s
              AND aml.date >= %s
              AND aml.date <= %s
              AND aml.tax_line_id IS NOT NULL
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
              {journal_clause}
            GROUP BY at.id, at.name, at.type_tax_use, atg.name, at.amount
            ORDER BY at.type_tax_use, atg.name, at.name
        """
        self.env.cr.execute(query_tax, (company_id, df, dt) + journal_params)
        tax_rows = self.env.cr.dictfetchall()

        # Query 2: Base amounts per tax (from the many2many relation on base lines)
        query_base = f"""
            SELECT
                amlat.account_tax_id AS tax_id,
                COALESCE(SUM(aml.debit - aml.credit), 0.0) AS base_amount
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_move_line_account_tax_rel amlat ON amlat.account_move_line_id = aml.id
            WHERE aml.company_id = %s
              AND aml.date >= %s
              AND aml.date <= %s
              AND aml.tax_line_id IS NULL
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
              {journal_clause}
            GROUP BY amlat.account_tax_id
        """
        self.env.cr.execute(query_base, (company_id, df, dt) + journal_params)
        base_rows = self.env.cr.dictfetchall()
        base_by_tax = {r['tax_id']: r['base_amount'] for r in base_rows}

        # Helper to extract translation from JSONB dict returned by SQL
        lang = self.env.user.lang or 'en_US'
        def get_trans(val):
            if isinstance(val, dict):
                return val.get(lang) or val.get('en_US') or (list(val.values())[0] if val else '')
            return val

        # Build structured result
        groups = {}
        for row in tax_rows:
            tax_type = row['tax_type']
            group_name = get_trans(row['tax_group_name']) or _('Ungrouped')
            tax_name = get_trans(row['tax_name']) or _('Unnamed Tax')
            key = (tax_type, group_name)

            if key not in groups:
                groups[key] = {
                    'type': tax_type,
                    'type_label': 'Sales Tax' if tax_type == 'sale' else 'Purchase Tax',
                    'group_name': group_name,
                    'taxes': [],
                    'total_base': 0.0,
                    'total_tax': 0.0,
                }

            base = base_by_tax.get(row['tax_id'], 0.0)
            tax_amount = abs(row['tax_amount'])  # show as positive
            base_amount = abs(base)

            groups[key]['taxes'].append({
                'tax_id': row['tax_id'],
                'name': tax_name,
                'rate': row['tax_rate'],
                'base_amount': base_amount,
                'tax_amount': tax_amount,
            })
            groups[key]['total_base'] += base_amount
            groups[key]['total_tax'] += tax_amount

        # Sort into sale/purchase sections
        sale_groups = [g for g in groups.values() if g['type'] == 'sale']
        purchase_groups = [g for g in groups.values() if g['type'] == 'purchase']

        total_sale_tax = sum(g['total_tax'] for g in sale_groups)
        total_purchase_tax = sum(g['total_tax'] for g in purchase_groups)
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
