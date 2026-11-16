from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    next_appraisal_date = fields.Date(
        string='Next Appraisal Date', tracking=True, groups="hr.group_hr_user",
        help="Computed from the Appraisals Plans of the company: first appraisal after the recruitment, "
             "the second one after the first, then periodically.")
    appraisal_count = fields.Integer(compute='_compute_appraisal_count', string="Appraisals")

    def _compute_appraisal_count(self):
        data = self.env['hr.appraisal']._read_group([('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in data}
        for employee in self:
            employee.appraisal_count = counts.get(employee.id, 0)

    def _get_next_appraisal_date_from_plan(self):
        """ Next appraisal date according to the Appraisals Plans of the company. """
        self.ensure_one()
        employee = self.sudo()
        company = employee.company_id or self.env.company
        done = self.env['hr.appraisal'].sudo().search(
            [('employee_id', '=', employee.id), ('state', '=', 'done')], order='date_done desc, id desc')
        if not done:
            start = employee.first_contract_date or (employee.create_date and employee.create_date.date()) or fields.Date.today()
            return start + relativedelta(months=company.appraisal_plan_first_month)
        last_date = done[0].date_done or done[0].date_appraisal
        months = company.appraisal_plan_next_month if len(done) == 1 else company.appraisal_plan_recurring_month
        return last_date + relativedelta(months=months)

    def _set_next_appraisal_date_from_plan(self):
        for employee in self.sudo():
            if employee.company_id.appraisal_plan:
                employee.next_appraisal_date = employee._get_next_appraisal_date_from_plan()

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.sudo().filtered(lambda e: not e.next_appraisal_date)._set_next_appraisal_date_from_plan()
        return employees

    def action_open_appraisals(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('eh_hr_appraisal.action_hr_appraisal')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action
