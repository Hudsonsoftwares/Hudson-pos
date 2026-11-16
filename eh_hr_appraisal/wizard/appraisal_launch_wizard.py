from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _


class AppraisalLaunchWizard(models.TransientModel):
    _name = 'hr.appraisal.launch.wizard'
    _description = 'Launch Appraisal Campaign'

    def _default_employees(self):
        if self.env.context.get('active_model') == 'hr.employee' and self.env.context.get('active_ids'):
            return self.env['hr.employee'].browse(self.env.context.get('active_ids'))
        return False

    employee_ids = fields.Many2many(
        'hr.employee', string="Employees", default=_default_employees, bypass_search_access=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]")
    template_id = fields.Many2one(
        'hr.appraisal.template', string="Appraisal Template",
        help="Leave empty to use the template of each employee's department, or the default one.")
    date_appraisal = fields.Date(
        string="Appraisal Date", required=True,
        default=lambda self: fields.Date.context_today(self) + relativedelta(months=1))
    no_manager_warning = fields.Char(compute="_compute_no_manager_warning")

    @api.model_create_multi
    def create(self, vals_list):
        # Employees are readable by HR officers only in Odoo 20
        # sudo() drops the default_* context keys: apply the defaults first
        vals_list = [self._add_missing_default_values(vals) for vals in vals_list]
        return super(AppraisalLaunchWizard, self.sudo()).create(vals_list).sudo(False)

    def write(self, vals):
        return super(AppraisalLaunchWizard, self.sudo()).write(vals)

    def _get_employees(self):
        return self.employee_ids or self.env['hr.employee'].search([('company_id', 'in', self.env.companies.ids)])

    @api.depends('employee_ids')
    def _compute_no_manager_warning(self):
        for wizard in self:
            no_manager = wizard._get_employees().filtered(lambda e: not e.parent_id)
            wizard.no_manager_warning = _(
                "These employees have no manager, appraisals are created without appraiser: %s",
                ', '.join(no_manager.mapped('name'))) if no_manager else False

    def action_launch(self):
        self.ensure_one()
        Appraisal = self.env['hr.appraisal']
        employees = self._get_employees()
        busy = Appraisal.search([('employee_id', 'in', employees.ids), ('state', 'in', ['draft', 'ongoing'])]).employee_id
        vals_list = []
        for employee in employees - busy:
            vals = {'employee_id': employee.id, 'date_appraisal': self.date_appraisal}
            template = self.template_id
            if template and (not template.company_id or template.company_id == employee.company_id):
                vals['template_id'] = template.id
            vals_list.append(vals)
        Appraisal.create(vals_list)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Campaign Launched'),
                'message': _('%(count)s appraisals scheduled, %(skipped)s employees already had one in progress.',
                             count=len(vals_list), skipped=len(busy)),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
