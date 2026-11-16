from odoo import api, fields, models, _


class HrAppraisalGoal(models.Model):
    _name = "hr.appraisal.goal"
    _description = "Appraisal Goal"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "deadline, id"
    _check_company_auto = True

    name = fields.Char(string="Goal", required=True, tracking=True)
    employee_id = fields.Many2one(
        'hr.employee', string="Employee", required=True, tracking=True, index=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]")
    # A goal always belongs to the company of its employee
    company_id = fields.Many2one('res.company', string="Company", related='employee_id.company_id', store=True, index=True)
    manager_id = fields.Many2one(
        'hr.employee', string="Manager", compute='_compute_manager_id', store=True, readonly=False, tracking=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]")
    appraisal_id = fields.Many2one(
        'hr.appraisal', string="Appraisal", domain="[('employee_id', '=', employee_id)]", check_company=True, index=True)
    template_id = fields.Many2one('hr.appraisal.goal.template', string="Goal Template", readonly=True)
    employee_avatar = fields.Image(related='employee_id.avatar_128', string="Employee Avatar")
    description = fields.Html(string="Description")
    deadline = fields.Date(string="Deadline", tracking=True)
    progress = fields.Selection([
        ('0', '0%'),
        ('25', '25%'),
        ('50', '50%'),
        ('75', '75%'),
        ('100', '100%'),
    ], string="Progress", default='0', required=True, tracking=True)
    tag_ids = fields.Many2many('hr.appraisal.goal.tag', string="Tags")
    state = fields.Selection([
        ('draft', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
    ], string="Status", compute='_compute_state', store=True)
    is_late = fields.Boolean(compute='_compute_is_late')

    @api.depends('employee_id')
    def _compute_manager_id(self):
        for goal in self:
            goal.manager_id = goal.employee_id.sudo().parent_id

    @api.depends('progress')
    def _compute_state(self):
        for goal in self:
            if goal.progress == '100':
                goal.state = 'done'
            elif goal.progress == '0':
                goal.state = 'draft'
            else:
                goal.state = 'in_progress'

    @api.depends('deadline', 'progress')
    def _compute_is_late(self):
        today = fields.Date.context_today(self)
        for goal in self:
            goal.is_late = bool(goal.deadline and goal.progress != '100' and goal.deadline < today)

    @api.onchange('appraisal_id')
    def _onchange_appraisal_id(self):
        if self.appraisal_id and not self.employee_id:
            self.employee_id = self.appraisal_id.employee_id

    def action_mark_as_done(self):
        self.write({'progress': '100'})
        return True

    def action_save_as_template(self):
        self.ensure_one()
        template = self.env['hr.appraisal.goal.template'].create({
            'name': self.name,
            'description': self.description,
            'tag_ids': [(6, 0, self.tag_ids.ids)],
        })
        return {
            'name': _('Goals Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.appraisal.goal.template',
            'view_mode': 'form',
            'res_id': template.id,
            'target': 'current',
        }
