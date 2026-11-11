from collections import defaultdict
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.misc import formatLang
from lxml import etree


class AccountBudgetLine(models.Model):
    _name = 'account.budget.line'
    _inherit = ['account.budget.line', 'analytic.plan.fields.mixin']

    # Liquidation amount field: by default equals Commitment (planned_amount), editable by user
    liquidation_amount = fields.Monetary(
        string='Liquidation',
        currency_field='currency_id',
        compute='_compute_liquidation_amount',
        store=True,
        readonly=False,
        precompute=True,
    )
    is_liquidation_customized = fields.Boolean(
        string='Liquidation Customized',
        default=False,
        copy=True,
    )

    date_from = fields.Date(
        'Start Date',
        required=False,
        compute='_compute_dates',
        store=True,
        readonly=False,
        precompute=True,
    )
    date_to = fields.Date(
        'End Date',
        required=False,
        compute='_compute_dates',
        store=True,
        readonly=False,
        precompute=True,
    )

    def _register_hook(self):
        super()._register_hook()
        try:
            # Dynamically register onchange for all plan fields
            # Use the unbound function: Odoo calls onchange methods as method(record)
            onchange_method = type(self)._onchange_plan_accounts
            plan_fnames = self._get_plan_fnames()
            for fname in plan_fnames:
                if fname in self._fields and fname != 'account_id':
                    if onchange_method not in self._onchange_methods.setdefault(fname, []):
                        self._onchange_methods[fname].append(onchange_method)
        except Exception:
            pass

    @api.depends('planned_amount')
    def _compute_liquidation_amount(self):
        for line in self:
            if not line.is_liquidation_customized:
                line.liquidation_amount = line.planned_amount

    @api.onchange('liquidation_amount')
    def _onchange_liquidation_amount(self):
        for line in self:
            if line.liquidation_amount != line.planned_amount:
                line.is_liquidation_customized = True

    @api.onchange('planned_amount')
    def _onchange_planned_amount(self):
        for line in self:
            if not line.is_liquidation_customized:
                line.liquidation_amount = line.planned_amount

    @api.depends('budget_id.date_from', 'budget_id.date_to')
    def _compute_dates(self):
        for line in self:
            if line.budget_id:
                if not line.date_from:
                    line.date_from = line.budget_id.date_from
                if not line.date_to:
                    line.date_to = line.budget_id.date_to

    @api.onchange('account_id')
    def _onchange_plan_accounts(self):
        for line in self:
            for fname in line._get_plan_fnames():
                if fname in line._fields and line[fname]:
                    line.analytic_account_id = line[fname]
                    break

    @api.constrains('position_id', 'analytic_account_id', 'budget_id')
    def _check_position_or_analytic_account(self):
        plan_fnames = self._get_plan_fnames()
        for line in self:
            has_plan = any(line[fname] for fname in plan_fnames if fname in line._fields)
            if not line.analytic_account_id and not line.position_id and not has_plan:
                raise ValidationError(
                    _("You have to enter at least a budgetary position or analytic account on a budget line."))

    @api.model_create_multi
    def create(self, vals_list):
        plan_fnames = self._get_plan_fnames()
        for vals in vals_list:
            if 'planned_amount' in vals:
                if 'liquidation_amount' not in vals:
                    vals['liquidation_amount'] = vals['planned_amount']
                elif vals.get('liquidation_amount') != vals.get('planned_amount'):
                    vals['is_liquidation_customized'] = True

            # Sync analytic_account_id from any selected plan
            if not vals.get('analytic_account_id'):
                for fname in plan_fnames:
                    if vals.get(fname):
                        vals['analytic_account_id'] = vals[fname]
                        break
            # Sync plan field if analytic_account_id is provided
            if vals.get('analytic_account_id'):
                acc = self.env['account.analytic.account'].browse(vals['analytic_account_id'])
                if acc.exists() and acc.plan_id:
                    plan_col = acc.plan_id._column_name()
                    if plan_col in self._fields and not vals.get(plan_col):
                        vals[plan_col] = acc.id
        return super().create(vals_list)

    def write(self, vals):
        plan_fnames = self._get_plan_fnames()
        if not vals.get('analytic_account_id'):
            for fname in plan_fnames:
                if vals.get(fname):
                    vals['analytic_account_id'] = vals[fname]
                    break
        elif vals.get('analytic_account_id'):
            acc = self.env['account.analytic.account'].browse(vals['analytic_account_id'])
            if acc.exists() and acc.plan_id:
                plan_col = acc.plan_id._column_name()
                if plan_col in self._fields and not vals.get(plan_col):
                    vals[plan_col] = acc.id

        if 'liquidation_amount' in vals:
            for line in self:
                planned = vals.get('planned_amount', line.planned_amount)
                if vals['liquidation_amount'] != planned:
                    vals['is_liquidation_customized'] = True
        elif 'planned_amount' in vals and 'is_liquidation_customized' not in vals:
            for line in self:
                if not line.is_liquidation_customized:
                    super(AccountBudgetLine, line).write({'liquidation_amount': vals['planned_amount']})
        return super().write(vals)

    def _compute_practical_amount(self):
        plan_fnames = self._get_plan_fnames()
        lines_with_plans = self.filtered(lambda l: any(l[fname] for fname in plan_fnames if fname in l._fields))
        other_lines = self - lines_with_plans
        if other_lines:
            super(AccountBudgetLine, other_lines)._compute_practical_amount()

        for line in lines_with_plans:
            if not (line.date_from and line.date_to):
                line.practical_amount = 0.0
                continue
            domain = [
                ('date', '>=', line.date_from),
                ('date', '<=', line.date_to),
                ('company_id', 'in', [line.company_id.id, False]),
            ]
            for fname in plan_fnames:
                if fname in line._fields and line[fname]:
                    domain.append((fname, '=', line[fname].id))

            if line.position_id and line.position_id.account_ids:
                domain.append(('general_account_id', 'in', line.position_id.account_ids.ids))
            elif line.budget_type == 'expense':
                domain.append(('general_account_id.account_type', 'in', ['expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost']))
            elif line.budget_type == 'revenue':
                domain.append(('general_account_id.account_type', 'in', ['income', 'income_other']))

            result = self.env['account.analytic.line']._read_group(domain, aggregates=['amount:sum'])
            amount = result[0][0] or 0.0 if result else 0.0
            line.practical_amount = -amount if line.budget_type == 'expense' else amount

    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)
        if self.env['account.analytic.plan'].has_access('read'):
            arch = self._patch_budget_line_views(arch, view_type)
        return arch, view

    def _patch_budget_line_views(self, arch, view_type):
        project_plan, other_plans = self.env['account.analytic.plan']._get_all_plans()
        if view_type == 'form':
            account_node = arch.find('.//field[@name="account_id"]')
            if account_node is not None:
                if project_plan:
                    account_node.attrib['string'] = project_plan[0].name
                    account_node.attrib['domain'] = repr([('plan_id', 'child_of', project_plan[0].id)])
                    account_node.attrib['context'] = repr({'default_plan_id': project_plan[0].id})
                existing_fnames = {node.attrib.get('name') for node in arch.findall('.//field')}
                curr_node = account_node
                for plan in other_plans:
                    fname = plan._column_name()
                    if fname not in existing_fnames and fname in self._fields:
                        new_node = etree.Element('field', {
                            'name': fname,
                            'string': plan.name,
                            'domain': repr([('plan_id', 'child_of', plan.id)]),
                            'context': repr({'default_plan_id': plan.id}),
                        })
                        curr_node.addnext(new_node)
                        curr_node = new_node
                        existing_fnames.add(fname)
        elif view_type in ('list', 'tree'):
            account_node = arch.find('.//field[@name="account_id"]')
            if account_node is not None:
                if project_plan:
                    account_node.attrib['string'] = project_plan[0].name
                    account_node.attrib['domain'] = repr([('plan_id', 'child_of', project_plan[0].id)])
                existing_fnames = {node.attrib.get('name') for node in arch.findall('.//field')}
                curr_node = account_node
                for plan in other_plans:
                    fname = plan._column_name()
                    if fname not in existing_fnames and fname in self._fields:
                        new_node = etree.Element('field', {
                            'name': fname,
                            'string': plan.name,
                            'optional': 'hide',
                            'domain': repr([('plan_id', 'child_of', plan.id)]),
                            'context': repr({'default_plan_id': plan.id}),
                        })
                        curr_node.addnext(new_node)
                        curr_node = new_node
                        existing_fnames.add(fname)
        return arch


class AccountBudget(models.Model):
    _inherit = 'account.budget'

    budget_type = fields.Selection([
        ('revenue', 'Revenue'),
        ('expense', 'Expense'),
        ('both', 'Both'),
    ], string='Budget Type', default='both', required=True, tracking=True)

    net_planned_amount = fields.Monetary('Planned Margin', compute='_compute_totals')
    net_theoretical_amount = fields.Monetary('Theoretical Margin', compute='_compute_totals')
    net_practical_amount = fields.Monetary('Actual Margin', compute='_compute_totals')
    net_achievement = fields.Float('Margin Achievement', compute='_compute_totals')

    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == 'form' and self.env['account.analytic.plan'].has_access('read'):
            arch = self._patch_budget_lines_view(arch)
        return arch, view

    def _patch_budget_lines_view(self, arch):
        project_plan, other_plans = self.env['account.analytic.plan']._get_all_plans()
        Line = self.env['account.budget.line']

        for line_list in arch.xpath("//field[@name='line_ids']//list | //field[@name='line_ids']//tree"):
            account_node = line_list.find('.//field[@name="account_id"]')
            if account_node is not None:
                if project_plan:
                    account_node.attrib['string'] = project_plan[0].name
                    account_node.attrib['domain'] = repr([('plan_id', 'child_of', project_plan[0].id)])
                    account_node.attrib['context'] = repr({'default_plan_id': project_plan[0].id})

                existing_nodes = {node.attrib.get('name'): node for node in line_list.findall('.//field')}
                curr_node = account_node
                for plan in other_plans:
                    fname = plan._column_name()
                    if fname in Line._fields:
                        if fname not in existing_nodes:
                            new_node = etree.Element('field', {
                                'name': fname,
                                'string': plan.name,
                                'optional': 'hide',
                                'options': "{'no_create_edit': False}",
                                'domain': repr([('plan_id', 'child_of', plan.id)]),
                                'context': repr({'default_plan_id': plan.id}),
                            })
                            curr_node.addnext(new_node)
                            curr_node = new_node
                            existing_nodes[fname] = new_node
                        else:
                            node = existing_nodes[fname]
                            node.attrib['string'] = plan.name
                            node.attrib['domain'] = repr([('plan_id', 'child_of', plan.id)])
                            node.attrib['context'] = repr({'default_plan_id': plan.id})
                            curr_node = node

        # Also patch any embedded form view under line_ids
        for line_form in arch.xpath("//field[@name='line_ids']//form"):
            account_node = line_form.find('.//field[@name="account_id"]')
            if account_node is not None:
                if project_plan:
                    account_node.attrib['string'] = project_plan[0].name
                    account_node.attrib['domain'] = repr([('plan_id', 'child_of', project_plan[0].id)])
                    account_node.attrib['context'] = repr({'default_plan_id': project_plan[0].id})

                existing_nodes = {node.attrib.get('name'): node for node in line_form.findall('.//field')}
                curr_node = account_node
                for plan in other_plans:
                    fname = plan._column_name()
                    if fname in Line._fields:
                        if fname not in existing_nodes:
                            new_node = etree.Element('field', {
                                'name': fname,
                                'string': plan.name,
                                'domain': repr([('plan_id', 'child_of', plan.id)]),
                                'context': repr({'default_plan_id': plan.id}),
                            })
                            curr_node.addnext(new_node)
                            curr_node = new_node
                            existing_nodes[fname] = new_node
                        else:
                            node = existing_nodes[fname]
                            node.attrib['string'] = plan.name
                            node.attrib['domain'] = repr([('plan_id', 'child_of', plan.id)])
                            node.attrib['context'] = repr({'default_plan_id': plan.id})
                            curr_node = node
        return arch

    @api.onchange('budget_type')
    def _onchange_budget_type(self):
        for budget in self:
            if budget.budget_type in ('expense', 'revenue'):
                for line in budget.line_ids:
                    line.budget_type = budget.budget_type

    @api.depends('budget_type', 'line_ids.planned_amount', 'line_ids.budget_type', 'line_ids.date_from', 'line_ids.date_to')
    def _compute_totals(self):
        self.line_ids.mapped('practical_amount')
        for budget in self:
            expense_lines = budget.line_ids.filtered(lambda l: l.budget_type == 'expense')
            exp_planned = sum(expense_lines.mapped('planned_amount'))
            exp_theoretical = sum(expense_lines.mapped('theoretical_amount'))
            exp_practical = sum(expense_lines.mapped('practical_amount'))
            budget.expense_planned_amount = exp_planned
            budget.expense_theoretical_amount = exp_theoretical
            budget.expense_practical_amount = exp_practical
            budget.expense_achievement = exp_practical / exp_theoretical if exp_theoretical else 0.0

            revenue_lines = budget.line_ids.filtered(lambda l: l.budget_type == 'revenue')
            rev_planned = sum(revenue_lines.mapped('planned_amount'))
            rev_theoretical = sum(revenue_lines.mapped('theoretical_amount'))
            rev_practical = sum(revenue_lines.mapped('practical_amount'))
            budget.revenue_planned_amount = rev_planned
            budget.revenue_theoretical_amount = rev_theoretical
            budget.revenue_practical_amount = rev_practical
            budget.revenue_achievement = rev_practical / rev_theoretical if rev_theoretical else 0.0

            both_lines = budget.line_ids.filtered(lambda l: l.budget_type == 'both')
            both_planned = sum(both_lines.mapped('planned_amount'))
            both_theoretical = sum(both_lines.mapped('theoretical_amount'))
            both_practical = sum(both_lines.mapped('practical_amount'))

            net_planned = rev_planned - exp_planned + both_planned
            net_theoretical = rev_theoretical - exp_theoretical + both_theoretical
            net_practical = rev_practical - exp_practical + both_practical
            budget.net_planned_amount = net_planned
            budget.net_theoretical_amount = net_theoretical
            budget.net_practical_amount = net_practical
            budget.net_achievement = net_practical / net_theoretical if net_theoretical else 0.0

            budget.is_over_budget = budget.state in ('validate', 'done') and any(
                line.is_over_budget for line in budget.line_ids if line.budget_type == 'expense'
            )

    def action_revise_budget(self):
        self.ensure_one()
        base_name = self.name
        if " - Rev " in base_name:
            base_name = base_name.rsplit(" - Rev ", 1)[0]

        existing_revisions = self.search([('name', 'ilike', f"{base_name} - Rev %")])
        rev_num = 1
        for rev in existing_revisions:
            try:
                num = int(rev.name.rsplit(" - Rev ", 1)[-1])
                if num >= rev_num:
                    rev_num = num + 1
            except ValueError:
                pass

        new_name = f"{base_name} - Rev {rev_num}"
        new_budget = self.copy(default={'name': new_name, 'state': 'draft', 'budget_type': self.budget_type})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Budget Revision'),
            'res_model': 'account.budget',
            'view_mode': 'form',
            'res_id': new_budget.id,
            'target': 'current',
        }
