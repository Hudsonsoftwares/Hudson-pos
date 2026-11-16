from datetime import datetime, time

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrAppraisalAskFeedback(models.TransientModel):
    _name = 'hr.appraisal.ask.feedback'
    _description = 'Ask Feedback for Appraisal'

    appraisal_id = fields.Many2one('hr.appraisal', required=True, ondelete='cascade')
    employee_id = fields.Many2one(related='appraisal_id.employee_id')
    survey_template_id = fields.Many2one(
        'survey.survey', string='Survey', required=True,
        domain=[('survey_type', '=', 'appraisal'), ('active', '=', True)],
        default=lambda self: self._default_survey_template())
    employee_ids = fields.Many2many(
        'hr.employee', string='Recipients', required=True, bypass_search_access=True,
        domain="[('id', '!=', employee_id), '|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]")
    deadline = fields.Date(string='Answer Deadline', compute='_compute_deadline', store=True, readonly=False, precompute=True)
    subject = fields.Char(string='Subject', compute='_compute_subject', store=True, readonly=False, precompute=True)
    body = fields.Html(string='Comments')

    @api.model_create_multi
    def create(self, vals_list):
        # Recipients are employees, readable by HR officers only in Odoo 20
        # sudo() drops the default_* context keys: apply the defaults first
        vals_list = [self._add_missing_default_values(vals) for vals in vals_list]
        return super(HrAppraisalAskFeedback, self.sudo()).create(vals_list).sudo(False)

    def write(self, vals):
        return super(HrAppraisalAskFeedback, self.sudo()).write(vals)

    def _default_survey_template(self):
        survey = self.env.company.sudo().appraisal_survey_template_id
        if not survey:
            survey = self.env['survey.survey'].sudo().search([('survey_type', '=', 'appraisal'), ('active', '=', True)], limit=1)
        return survey.id

    @api.depends('appraisal_id')
    def _compute_deadline(self):
        for wizard in self:
            wizard.deadline = wizard.appraisal_id.date_appraisal

    @api.depends('employee_id')
    def _compute_subject(self):
        for wizard in self:
            wizard.subject = _("Take part in %s appraisal", wizard.employee_id.name) if wizard.employee_id else False

    @staticmethod
    def _get_partner(employee):
        return employee.user_id.partner_id or employee.work_contact_id

    def action_send(self):
        self.ensure_one()
        appraisal = self.appraisal_id
        if not appraisal._is_appraiser():
            raise UserError(_("Only the appraisers can ask for 360 feedback."))
        if appraisal.state != 'ongoing':
            raise UserError(_("Feedback can only be requested on confirmed appraisals."))
        employees = self.employee_ids.sudo()
        missing = employees.filtered(lambda e: not (self._get_partner(e).email))
        if missing:
            raise UserError(_("These colleagues have no email address: %s", ', '.join(missing.mapped('name'))))

        survey = self.survey_template_id.sudo()
        deadline = datetime.combine(self.deadline, time.max.replace(microsecond=0)) if self.deadline else False
        UserInput = self.env['survey.user_input'].sudo()
        template = self.env.ref('eh_hr_appraisal.mail_template_appraisal_ask_feedback')
        for employee in employees:
            partner = self._get_partner(employee)
            # Resend: reuse the pending request of this colleague
            answer = UserInput.search([
                ('appraisal_id', '=', appraisal.id), ('survey_id', '=', survey.id),
                ('partner_id', '=', partner.id), ('state', '!=', 'done'), ('test_entry', '=', False),
            ], limit=1)
            if answer:
                answer.deadline = deadline
            else:
                answer = survey._create_answer(
                    partner=partner, check_attempts=False, deadline=deadline,
                    appraisal_id=appraisal.id, appraisal_employee_id=employee.id)
            template.sudo().with_context(
                appraisal_feedback_comment=self.body or '',
                appraisal_feedback_sender=self.env.user.name,
            ).send_mail(answer.id, email_values={'subject': self.subject}, email_layout_xmlid='mail.mail_notification_light')

        appraisal.sudo().message_post(body=_(
            "360 feedback requested by %(user)s from %(recipients)s.",
            user=self.env.user.name, recipients=', '.join(employees.mapped('name'))))
        return {'type': 'ir.actions.act_window_close'}
