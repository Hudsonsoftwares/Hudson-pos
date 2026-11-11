from odoo import models, api, fields
from lxml import etree
from lxml.builder import E

class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    def _patch_view(self, arch, view, view_type):
        arch, view = super()._patch_view(arch, view, view_type)
        if self.env['account.analytic.plan'].has_access('read'):
            project_plan, other_plans = self.env['account.analytic.plan']._get_all_plans()
            all_plans = project_plan + other_plans

            if view_type == 'search':
                account_filter_node = arch.find('.//filter[@name="account_id"]')
                if account_filter_node is not None:
                    # Make sure root project plan has proper label
                    if project_plan:
                        account_filter_node.set('string', project_plan.name or 'Project Plan')
                    
                    # Ensure all other plans have filters with their exact plan names
                    curr_node = account_filter_node
                    for plan in other_plans:
                        fname = plan._column_name()
                        existing_node = arch.find(f'.//filter[@name="{fname}"]')
                        if existing_node is not None:
                            existing_node.set('string', plan.name)
                            curr_node = existing_node
                        else:
                            new_filter = E.filter(
                                name=fname,
                                string=plan.name,
                                context=f"{{'group_by': '{fname}'}}"
                            )
                            curr_node.addnext(new_filter)
                            curr_node = new_filter

            elif view_type == 'pivot':
                # Ensure all analytic plan fields are present as groupable fields in the pivot view
                for plan in all_plans:
                    fname = plan._column_name()
                    if fname in self._fields:
                        existing_field = arch.find(f'.//field[@name="{fname}"]')
                        if existing_field is None:
                            arch.append(E.field(name=fname, string=plan.name))

        return arch, view

    @api.model
    def get_grid_data(self, domain=None, anchor_date=None, range_type='year'):
        """
        Returns structured matrix data for Analytic Grid View.
        Columns: periods (e.g. 12 months for year, or days for month).
        Rows: Analytic Accounts, with cell amounts and constituent line items.
        """
        import datetime
        from dateutil.relativedelta import relativedelta

        if not anchor_date:
            anchor = fields.Date.context_today(self)
        elif isinstance(anchor_date, str):
            anchor = fields.Date.from_string(anchor_date)
        else:
            anchor = anchor_date

        domain = domain or []
        company = self.env.company
        currency = company.currency_id

        # Determine columns based on range_type
        columns = []
        if range_type == 'month':
            # Days of the month
            start_date = anchor.replace(day=1)
            end_date = (start_date + relativedelta(months=1)) - datetime.timedelta(days=1)
            curr = start_date
            while curr <= end_date:
                columns.append({
                    'key': curr.strftime('%Y-%m-%d'),
                    'label': curr.strftime('%d %b'),
                    'start_date': curr.strftime('%Y-%m-%d'),
                    'end_date': curr.strftime('%Y-%m-%d'),
                })
                curr += datetime.timedelta(days=1)
        else:
            # Default 'year': 12 months of anchor's year
            start_date = datetime.date(anchor.year, 1, 1)
            end_date = datetime.date(anchor.year, 12, 31)
            for m in range(1, 13):
                m_start = datetime.date(anchor.year, m, 1)
                m_end = (m_start + relativedelta(months=1)) - datetime.timedelta(days=1)
                columns.append({
                    'key': f"{anchor.year}-{m:02d}",
                    'label': m_start.strftime('%B %Y'),
                    'start_date': m_start.strftime('%Y-%m-%d'),
                    'end_date': m_end.strftime('%Y-%m-%d'),
                })

        # Query analytic lines
        full_domain = domain + [
            ('date', '>=', start_date.strftime('%Y-%m-%d')),
            ('date', '<=', end_date.strftime('%Y-%m-%d')),
        ]
        lines = self.search(full_domain, order='date desc, id desc')

        # Group lines by analytic account
        account_data = {}
        for line in lines:
            acc = line.account_id
            acc_id = acc.id or 0
            acc_name = acc.display_name or 'No Analytic Account'

            if acc_id not in account_data:
                account_data[acc_id] = {
                    'id': acc_id,
                    'name': acc_name,
                    'code': acc.code or '',
                    'total': 0.0,
                    'values': {col['key']: 0.0 for col in columns},
                    'lines_by_name': {},
                }

            col_key = line.date.strftime('%Y-%m-%d') if range_type == 'month' else line.date.strftime('%Y-%m')
            amt = line.amount

            if col_key in account_data[acc_id]['values']:
                account_data[acc_id]['values'][col_key] += amt
            account_data[acc_id]['total'] += amt

            # Sub-row grouping by line name/description (or 'None' if blank)
            sub_name = line.name or 'None'
            if sub_name not in account_data[acc_id]['lines_by_name']:
                account_data[acc_id]['lines_by_name'][sub_name] = {
                    'name': sub_name,
                    'total': 0.0,
                    'values': {col['key']: 0.0 for col in columns},
                }
            if col_key in account_data[acc_id]['lines_by_name'][sub_name]['values']:
                account_data[acc_id]['lines_by_name'][sub_name]['values'][col_key] += amt
            account_data[acc_id]['lines_by_name'][sub_name]['total'] += amt

        # Format rows and compute column totals
        rows = []
        column_totals = {col['key']: 0.0 for col in columns}
        grand_total = 0.0

        for acc_id, data in sorted(account_data.items(), key=lambda x: x[1]['name'].lower()):
            subrows = []
            for sub_name, sub_info in sorted(data['lines_by_name'].items(), key=lambda x: x[0]):
                subrows.append({
                    'name': sub_name,
                    'total': sub_info['total'],
                    'values': sub_info['values'],
                })

            rows.append({
                'id': data['id'],
                'name': data['name'],
                'code': data['code'],
                'total': data['total'],
                'values': data['values'],
                'subrows': subrows,
            })

            for col_key, val in data['values'].items():
                column_totals[col_key] += val
            grand_total += data['total']

        return {
            'anchor_date': anchor.strftime('%Y-%m-%d'),
            'range_type': range_type,
            'period_label': anchor.strftime('%Y') if range_type == 'year' else anchor.strftime('%B %Y'),
            'columns': columns,
            'rows': rows,
            'column_totals': column_totals,
            'grand_total': grand_total,
            'currency_symbol': currency.symbol or '$',
            'currency_position': currency.position or 'before',
        }
