from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import is_html_empty


# Field families of an appraisal, used to decide who may write what.
HEADER_FIELDS = {'employee_id', 'appraiser_ids', 'date_appraisal', 'template_id', 'department_id', 'job_id'}
MANAGER_FIELDS = {'manager_feedback', 'manager_feedback_published', 'rating_id', 'target_job_id'}
PRIVATE_FIELDS = {'private_note'}
EMPLOYEE_FIELDS = {'employee_feedback', 'employee_feedback_published'}
CONTENT_FIELDS = HEADER_FIELDS | MANAGER_FIELDS | PRIVATE_FIELDS | EMPLOYEE_FIELDS


class HrAppraisal(models.Model):
    _name = "hr.appraisal"
    _description = "Employee Appraisal"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "date_appraisal desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Reference", required=True, copy=False, readonly=True, default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string="Employee to review", required=True, index=True, tracking=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]")
    manager_id = fields.Many2one('hr.employee', string="Manager", related="employee_id.parent_id", store=True)
    department_id = fields.Many2one(
        'hr.department', string="Department", compute='_compute_employee_data', store=True, readonly=False)
    job_id = fields.Many2one('hr.job', string="Job", compute='_compute_employee_data', store=True, readonly=False)
    # An appraisal always belongs to the company of the appraised employee
    company_id = fields.Many2one('res.company', string="Company", related='employee_id.company_id', store=True, index=True)

    appraiser_ids = fields.Many2many(
        'hr.employee', 'appraisal_appraiser_rel', 'appraisal_id', 'employee_id', string='Appraisers', tracking=True,
        bypass_search_access=True,
        domain="[('id', '!=', employee_id), '|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        help="Appraisers can read the shared self-assessment and fill in the Manager's Feedback.")
    date_appraisal = fields.Date(
        string="Appraisal Date", required=True, tracking=True,
        default=lambda self: fields.Date.context_today(self) + relativedelta(months=1),
        help="Date by which the appraisal should be completed.")
    date_done = fields.Date(string="Completion Date", readonly=True, copy=False)
    date_next = fields.Date(string="Next Appraisal Date", readonly=True, copy=False)
    template_id = fields.Many2one('hr.appraisal.template', string="Template", check_company=True)
    target_job_id = fields.Many2one(
        'hr.job', string="Target Job", tracking=True, check_company=True,
        help="Job position the employee is working towards. Its required skills are added to the Skills tab.")
    rating_id = fields.Many2one('hr.appraisal.scale', string="Final Rating", tracking=True, check_company=True)

    avatar_128 = fields.Image(related='employee_id.avatar_128', string="Avatar 128")
    avatar_1920 = fields.Image(related='employee_id.avatar_1920', string="Avatar")

    employee_feedback = fields.Html(string="Employee's Feedback")
    manager_feedback = fields.Html(string="Manager's Feedback")
    employee_feedback_published = fields.Boolean(string="Shared to Appraisers", default=False, tracking=True)
    manager_feedback_published = fields.Boolean(string="Shared to Employee", default=False, tracking=True)
    private_note = fields.Html(string="Private Note")

    state = fields.Selection([
        ('draft', 'To Confirm'),
        ('ongoing', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string="Status", default='draft', required=True, tracking=True, copy=False)

    goal_ids = fields.One2many('hr.appraisal.goal', 'appraisal_id', string="Goals")
    appraisal_skill_ids = fields.One2many('hr.appraisal.skill', 'appraisal_id', string="Skills")

    # Current user's rights, drive the form
    is_appraisal_manager = fields.Boolean(compute='_compute_user_rights')
    is_appraisal_employee = fields.Boolean(compute='_compute_user_rights')
    employee_feedback_visible = fields.Boolean(compute='_compute_user_rights')
    manager_feedback_visible = fields.Boolean(compute='_compute_user_rights')
    can_edit_employee_feedback = fields.Boolean(compute='_compute_user_rights')
    can_edit_manager_feedback = fields.Boolean(compute='_compute_user_rights')

    goal_count = fields.Integer(compute='_compute_goal_count')
    meeting_count = fields.Integer(compute='_compute_meeting_count')
    survey_answer_count = fields.Integer(compute='_compute_survey_answer_count')
    appraisal_360_feedback = fields.Boolean(related='company_id.appraisal_360_feedback')
    appraisal_plan = fields.Boolean(related='company_id.appraisal_plan')
    is_late = fields.Boolean(compute='_compute_is_late')

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    def _is_appraised_employee(self):
        """ The current user is the employee under review. """
        self.ensure_one()
        user = self.env.user
        return bool(self.employee_id) and (self.employee_id.sudo().user_id == user or self.employee_id in user.employee_ids)

    def _is_appraiser(self):
        """ The current user can act as appraiser: listed appraiser, manager in the
        employee's hierarchy, or appraisal officer. Nobody appraises themselves. """
        self.ensure_one()
        if self.env.su:
            return True
        if self._is_appraised_employee():
            return False
        user = self.env.user
        if user.has_group('eh_hr_appraisal.group_hr_appraisal_user'):
            return True
        user_employees = user.employee_ids
        if not user_employees:
            return False
        if self.appraiser_ids & user_employees:
            return True
        manager = self.employee_id.sudo().parent_id
        seen = set()
        while manager and manager.id not in seen:
            if manager in user_employees:
                return True
            seen.add(manager.id)
            manager = manager.parent_id
        return False

    def _can_read_employee_feedback(self):
        return self.env.su or self._is_appraised_employee() or self.employee_feedback_published

    def _can_read_manager_feedback(self):
        return self.env.su or self._is_appraiser() or self.manager_feedback_published

    @api.depends_context('uid')
    @api.depends('state', 'employee_id', 'appraiser_ids', 'employee_feedback_published', 'manager_feedback_published')
    def _compute_user_rights(self):
        for appraisal in self:
            is_manager = appraisal._is_appraiser()
            is_employee = appraisal._is_appraised_employee()
            appraisal.is_appraisal_manager = is_manager
            appraisal.is_appraisal_employee = is_employee
            appraisal.employee_feedback_visible = is_employee or appraisal.employee_feedback_published
            appraisal.manager_feedback_visible = is_manager or appraisal.manager_feedback_published
            appraisal.can_edit_employee_feedback = is_employee and appraisal.state == 'ongoing'
            appraisal.can_edit_manager_feedback = is_manager and appraisal.state == 'ongoing'

    def _read_format(self, fnames, load='_classic_read'):
        """ Private feedback never leaves the server for people who may not read it. """
        result = super()._read_format(fnames, load=load)
        if self.env.su or not {'employee_feedback', 'manager_feedback', 'private_note'} & set(fnames):
            return result
        records = {record.id: record for record in self}
        for vals in result:
            appraisal = records.get(vals['id'])
            if not appraisal or not appraisal._origin:
                continue  # record being created: nothing private yet
            if 'employee_feedback' in vals and not appraisal._can_read_employee_feedback():
                vals['employee_feedback'] = False
            if 'manager_feedback' in vals and not appraisal._can_read_manager_feedback():
                vals['manager_feedback'] = False
            if 'private_note' in vals and not appraisal._is_appraiser():
                vals['private_note'] = False
        return result

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('employee_id')
    def _compute_employee_data(self):
        for appraisal in self:
            employee = appraisal.employee_id.sudo()
            appraisal.department_id = employee.department_id
            appraisal.job_id = employee.job_id

    def _compute_goal_count(self):
        data = self.env['hr.appraisal.goal']._read_group(
            [('employee_id', 'in', self.employee_id.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in data}
        for appraisal in self:
            appraisal.goal_count = counts.get(appraisal.employee_id.id, 0)

    def _compute_meeting_count(self):
        data = self.env['calendar.event'].sudo()._read_group(
            [('res_model', '=', self._name), ('res_id', 'in', self.ids)], ['res_id'], ['__count'])
        counts = dict(data)
        for appraisal in self:
            appraisal.meeting_count = counts.get(appraisal.id, 0)

    def _compute_survey_answer_count(self):
        data = self.env['survey.user_input'].sudo()._read_group(
            [('appraisal_id', 'in', self.ids)], ['appraisal_id'], ['__count'])
        counts = {appraisal.id: count for appraisal, count in data}
        for appraisal in self:
            appraisal.survey_answer_count = counts.get(appraisal.id, 0)

    @api.depends('date_appraisal', 'state')
    def _compute_is_late(self):
        today = fields.Date.context_today(self)
        for appraisal in self:
            appraisal.is_late = bool(
                appraisal.state in ('draft', 'ongoing') and appraisal.date_appraisal and appraisal.date_appraisal < today)

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    @api.model
    def _get_default_template(self, employee):
        """ Template of the employee's department, else the general (Default) one. """
        Template = self.env['hr.appraisal.template']
        company_domain = ['|', ('company_id', '=', False), ('company_id', '=', employee.company_id.id)]
        if employee.department_id:
            template = Template.search(company_domain + [('department_ids', 'in', employee.department_id.ids)], limit=1)
            if template:
                return template
        return Template.search(company_domain + [('department_ids', '=', False)], limit=1)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if not self.employee_id:
            return
        employee = self.employee_id.sudo()
        # sudo: linking employees requires reading hr.employee (HR officers only)
        self.sudo().appraiser_ids = employee.parent_id
        self.template_id = self._get_default_template(employee)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env['hr.employee'].sudo().browse(vals.get('employee_id'))
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.appraisal') or _("Appraisal of %s", employee.name)
            if 'appraiser_ids' not in vals and employee.parent_id:
                vals['appraiser_ids'] = [(6, 0, employee.parent_id.ids)]
            if 'template_id' not in vals and employee:
                vals['template_id'] = self._get_default_template(employee).id
        # Linking employees requires reading hr.employee, which only HR officers may do
        # in Odoo 20. The appraisers are set as superuser once the creation is allowed.
        appraisers = [vals.pop('appraiser_ids', None) for vals in vals_list] if not self.env.su else []
        appraisals = super().create(vals_list)
        for appraisal, appraiser_commands in zip(appraisals, appraisers):
            if appraiser_commands:
                super(HrAppraisal, appraisal.sudo()).write({'appraiser_ids': appraiser_commands})
        appraisals._apply_template_feedback()
        return appraisals

    def write(self, vals):
        if not self.env.su:
            self._check_write_rights(vals)
            if 'appraiser_ids' in vals:
                vals = dict(vals)
                self.check_access('write')
                super(HrAppraisal, self.sudo()).write({'appraiser_ids': vals.pop('appraiser_ids')})
        old_templates = {record.id: record.template_id for record in self} if 'template_id' in vals else {}
        res = super().write(vals)
        if old_templates:
            self._apply_template_feedback(old_templates)
        if 'target_job_id' in vals:
            self.filtered(lambda a: a.state == 'ongoing')._populate_skills()
        return res

    def _check_write_rights(self, vals):
        keys = set(vals)
        for record in self:
            appraiser = record._is_appraiser()
            employee = record._is_appraised_employee()
            if 'state' in keys and not appraiser:
                raise UserError(_("Only the appraisers can change the status of an appraisal."))
            if 'state' not in keys and record.state in ('done', 'cancel') and keys & CONTENT_FIELDS:
                raise UserError(_("This appraisal is closed. Reopen it to make changes."))
            if keys & (HEADER_FIELDS | MANAGER_FIELDS | PRIVATE_FIELDS) and not appraiser:
                raise UserError(_("Only the appraisers can modify the appraisal settings, the manager's feedback, the rating and the private note."))
            if keys & MANAGER_FIELDS and record.state != 'ongoing' and 'state' not in keys:
                raise UserError(_("Confirm the appraisal before filling in the manager's feedback and the final rating."))
            employee_keys = keys & EMPLOYEE_FIELDS
            if employee_keys:
                # Appraisers may publish a self-assessment without the employee's consent (logged).
                force_publish = employee_keys == {'employee_feedback_published'} and vals['employee_feedback_published'] and appraiser
                if not employee and not force_publish:
                    raise UserError(_("Only %s can write and share this self-assessment.", record.employee_id.name))
                if record.state != 'ongoing' and 'state' not in keys:
                    raise UserError(_("The self-assessment can only be filled in once the appraisal is confirmed."))

    def _apply_template_feedback(self, old_templates=None):
        """ Pre-fill both feedback sections with the template questions.

        A section is only replaced while it is empty or still holds the
        untouched questions of the previous template, so written answers are
        never lost. Done as superuser: the template is chosen by the appraiser
        while the employee's section belongs to the employee.
        """
        old_templates = old_templates or {}
        for record in self.sudo().filtered('template_id'):
            old_template = old_templates.get(record.id, self.env['hr.appraisal.template']).sudo()
            vals = {}
            for field, template_field in (('employee_feedback', 'employee_feedback_template'),
                                          ('manager_feedback', 'manager_feedback_template')):
                current = record[field]
                if record.template_id[template_field] and (is_html_empty(current) or current == old_template[template_field]):
                    vals[field] = record.template_id[template_field]
            if vals:
                record.write(vals)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def _check_appraiser(self, message):
        for record in self:
            if not record._is_appraiser():
                raise UserError(message)

    def _get_notified_partners(self):
        self.ensure_one()
        employees = (self.employee_id | self.appraiser_ids).sudo()
        return employees.mapped(lambda e: e.user_id.partner_id or e.work_contact_id)

    def _get_confirmation_partner_ids(self):
        """ Used by the confirmation mail template. """
        return ','.join(str(pid) for pid in self._get_notified_partners().ids)

    def action_confirm(self):
        self._check_appraiser(_("Only the appraisers can confirm an appraisal."))
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Only appraisals to confirm can be confirmed."))
        self.sudo().write({'state': 'ongoing'})
        self._populate_skills()
        template = self.env.ref('eh_hr_appraisal.mail_template_appraisal_confirm', raise_if_not_found=False)
        for record in self:
            partners = record._get_notified_partners()
            record.sudo().message_subscribe(partner_ids=partners.ids)
            if template:
                template = template.sudo()
                record.sudo().message_post(
                    body=template._render_field('body_html', record.ids, compute_lang=True)[record.id],
                    subject=template._render_field('subject', record.ids, compute_lang=True)[record.id],
                    partner_ids=partners.ids,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                    email_layout_xmlid='mail.mail_notification_layout',
                )
            employee_user = record.employee_id.sudo().user_id
            if employee_user:
                record.sudo().activity_schedule(
                    'mail.mail_activity_data_todo', date_deadline=record.date_appraisal, user_id=employee_user.id,
                    summary=_("Fill in your self-assessment"),
                    note=_("Complete the Employee's Feedback section of your appraisal and share it with your appraisers."))
            for appraiser_user in record.appraiser_ids.sudo().user_id:
                record.sudo().activity_schedule(
                    'mail.mail_activity_data_todo', date_deadline=record.date_appraisal, user_id=appraiser_user.id,
                    summary=_("Appraisal of %s", record.employee_id.name),
                    note=_("Fill in the Manager's Feedback and meet %s to review the appraisal.", record.employee_id.name))
        return True

    def action_done(self):
        self._check_appraiser(_("Only the appraisers can mark an appraisal as done."))
        for record in self:
            if record.state != 'ongoing':
                raise UserError(_("Only confirmed appraisals can be marked as done."))
        today = fields.Date.context_today(self)
        self.sudo().write({'state': 'done', 'date_done': today})
        for record in self.sudo():
            record._update_employee_skills()
            record.activity_ids.action_feedback()
            employee = record.employee_id
            if employee.company_id.appraisal_plan:
                next_date = employee._get_next_appraisal_date_from_plan()
            else:
                next_date = (record.date_appraisal or today) + relativedelta(years=1)
            record.date_next = next_date
            employee.next_appraisal_date = next_date
        return True

    def action_reopen(self):
        self._check_appraiser(_("Only the appraisers can reopen an appraisal."))
        for record in self:
            if record.state != 'done':
                raise UserError(_("Only completed appraisals can be reopened."))
        self.sudo().write({'state': 'ongoing', 'date_done': False})
        return True

    def action_cancel(self):
        self._check_appraiser(_("Only the appraisers can cancel an appraisal."))
        self.sudo().write({'state': 'cancel'})
        self.sudo().activity_ids.unlink()
        return True

    def action_draft(self):
        self._check_appraiser(_("Only the appraisers can reset an appraisal."))
        for record in self:
            if record.state != 'cancel':
                raise UserError(_("Only cancelled appraisals can be reset to To Confirm."))
        self.sudo().write({'state': 'draft'})
        return True

    def action_publish_employee_feedback(self):
        for record in self:
            record.employee_feedback_published = True
            if not record._is_appraised_employee():
                record.message_post(body=_("The employee's feedback was shared to the appraisers by %s.", self.env.user.name))
        return True

    def action_unpublish_employee_feedback(self):
        self.write({'employee_feedback_published': False})
        return True

    def action_publish_manager_feedback(self):
        self.write({'manager_feedback_published': True})
        return True

    def action_unpublish_manager_feedback(self):
        self.write({'manager_feedback_published': False})
        return True

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def _populate_skills(self):
        """ Load the employee's current skills, then the skills of the target job. """
        AppraisalSkill = self.env['hr.appraisal.skill'].sudo()
        for record in self.sudo():
            known_skills = record.appraisal_skill_ids.skill_id
            vals_list = []
            if not record.appraisal_skill_ids:
                for employee_skill in record.employee_id.current_employee_skill_ids:
                    if employee_skill.is_certification or employee_skill.skill_id in known_skills:
                        continue
                    known_skills |= employee_skill.skill_id
                    vals_list.append({
                        'appraisal_id': record.id,
                        'skill_type_id': employee_skill.skill_type_id.id,
                        'skill_id': employee_skill.skill_id.id,
                        'skill_level_id': employee_skill.skill_level_id.id,
                        'previous_skill_level_id': employee_skill.skill_level_id.id,
                        'previous_level_progress': employee_skill.skill_level_id.level_progress,
                    })
            for job_skill in record.target_job_id.current_job_skill_ids:
                if job_skill.is_certification or job_skill.skill_id in known_skills:
                    continue
                known_skills |= job_skill.skill_id
                vals_list.append({
                    'appraisal_id': record.id,
                    'skill_type_id': job_skill.skill_type_id.id,
                    'skill_id': job_skill.skill_id.id,
                })
            if vals_list:
                AppraisalSkill.create(vals_list)

    def _update_employee_skills(self):
        """ Write the levels validated during the appraisal back to the employee. """
        self.ensure_one()
        employee = self.employee_id.sudo()
        current = {skill.skill_id: skill for skill in employee.current_employee_skill_ids}
        commands = []
        for line in self.appraisal_skill_ids.filtered('skill_level_id'):
            employee_skill = current.get(line.skill_id)
            if employee_skill:
                if employee_skill.skill_level_id != line.skill_level_id:
                    commands.append((1, employee_skill.id, {'skill_level_id': line.skill_level_id.id}))
            else:
                commands.append((0, 0, {
                    'skill_type_id': line.skill_type_id.id,
                    'skill_id': line.skill_id.id,
                    'skill_level_id': line.skill_level_id.id,
                }))
        if commands:
            employee.write({'employee_skill_ids': commands})

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_open_goals(self):
        self.ensure_one()
        return {
            'name': _('Goals'),
            'type': 'ir.actions.act_window',
            'view_mode': 'list,kanban,form',
            'res_model': 'hr.appraisal.goal',
            'domain': [('employee_id', '=', self.employee_id.id)],
            'context': {
                'default_employee_id': self.employee_id.id,
                'default_appraisal_id': self.id,
            },
        }

    def action_ask_feedback(self):
        self.ensure_one()
        self._check_appraiser(_("Only the appraisers can ask for 360 feedback."))
        if self.state != 'ongoing':
            raise UserError(_("Confirm the appraisal before asking for feedback."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ask Feedback'),
            'res_model': 'hr.appraisal.ask.feedback',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_appraisal_id': self.id},
        }

    def action_open_survey_inputs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('eh_hr_appraisal.action_hr_appraisal_feedback_inputs')
        action['domain'] = [('appraisal_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    def action_schedule_meeting(self):
        self.ensure_one()
        self._check_appraiser(_("Only the appraisers can schedule the appraisal meeting."))
        partners = self._get_notified_partners()
        return {
            'name': _('Meetings'),
            'type': 'ir.actions.act_window',
            'res_model': 'calendar.event',
            'view_mode': 'calendar,list,form',
            'context': {
                'default_name': _("Appraisal of %s", self.employee_id.name),
                'default_partner_ids': partners.ids,
                'default_res_model_id': self.env['ir.model']._get_id(self._name),
                'default_res_id': self.id,
                'default_start': fields.Datetime.to_string(fields.Datetime.now()),
                'initial_date': fields.Date.to_string(self.date_appraisal or fields.Date.context_today(self)),
            },
        }

    def action_open_meetings(self):
        self.ensure_one()
        if not self.meeting_count:
            return self.action_schedule_meeting()
        action = self.action_schedule_meeting()
        action['domain'] = [('res_model', '=', self._name), ('res_id', '=', self.id)]
        action['view_mode'] = 'list,calendar,form'
        return action

    # ------------------------------------------------------------------
    # Crons
    # ------------------------------------------------------------------

    @api.model
    def _cron_send_reminders(self):
        """ Warn the appraisers once an appraisal is overdue. """
        today = fields.Date.context_today(self)
        overdue = self.search([('state', 'in', ['draft', 'ongoing']), ('date_appraisal', '<', today)])
        warning_type = self.env.ref('mail.mail_activity_data_warning')
        for appraisal in overdue:
            if appraisal.activity_ids.filtered(lambda a: a.activity_type_id == warning_type):
                continue
            user = appraisal.appraiser_ids.user_id[:1] or appraisal.manager_id.user_id
            if not user:
                continue
            appraisal.activity_schedule(
                'mail.mail_activity_data_warning', user_id=user.id, date_deadline=today,
                summary=_("Overdue Appraisal"),
                note=_("The appraisal of %s is overdue.", appraisal.employee_id.name))

    @api.model
    def _cron_appraisal_automation(self):
        """ Appraisals Automation: create and confirm the appraisals planned by
        the Appraisals Plans one month before their date. """
        today = fields.Date.context_today(self)
        companies = self.env['res.company'].search([('appraisal_automation', '=', True), ('appraisal_plan', '=', True)])
        employees = self.env['hr.employee'].search([
            ('company_id', 'in', companies.ids),
            ('next_appraisal_date', '!=', False),
            ('next_appraisal_date', '<=', today + relativedelta(months=1)),
        ])
        open_employees = self.search([
            ('employee_id', 'in', employees.ids), ('state', 'in', ['draft', 'ongoing']),
        ]).employee_id
        for employee in employees - open_employees:
            appraisal = self.with_company(employee.company_id).create({
                'employee_id': employee.id,
                'date_appraisal': max(employee.next_appraisal_date, today),
            })
            appraisal.action_confirm()
