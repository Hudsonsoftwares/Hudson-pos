from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrAppraisalGoalAssign(models.TransientModel):
    _name = 'hr.appraisal.goal.assign'
    _description = 'Assign Goals to Employees'

    template_ids = fields.Many2many('hr.appraisal.goal.template', string="Goals", required=True)
    employee_ids = fields.Many2many(
        'hr.employee', string="Employees", bypass_search_access=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]")

    @api.model_create_multi
    def create(self, vals_list):
        # Employees are readable by HR officers only in Odoo 20; the goals
        # themselves are created with the user's rights in action_add_goals
        # sudo() drops the default_* context keys: apply the defaults first
        vals_list = [self._add_missing_default_values(vals) for vals in vals_list]
        return super(HrAppraisalGoalAssign, self.sudo()).create(vals_list).sudo(False)

    def write(self, vals):
        return super(HrAppraisalGoalAssign, self.sudo()).write(vals)

    def action_add_goals(self):
        self.ensure_one()
        if not self.employee_ids:
            raise UserError(_("Select at least one employee."))
        today = fields.Date.context_today(self)
        vals_list = []
        for employee in self.employee_ids:
            for template in self.template_ids:
                vals_list.append({
                    'name': template.name,
                    'employee_id': employee.id,
                    'description': template.description,
                    'tag_ids': [(6, 0, template.tag_ids.ids)],
                    'template_id': template.id,
                    'deadline': today + relativedelta(months=template.timing) if template.timing else False,
                })
        self.env['hr.appraisal.goal'].create(vals_list)
        return {
            'type': 'ir.actions.act_window_close',
            'infos': {'reload': True},
        }
