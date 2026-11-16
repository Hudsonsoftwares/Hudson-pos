from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ReferralPromote(models.TransientModel):
    _name = 'eh.hr.referral.promote'
    _description = 'Promote Job Position to Employees'

    job_id = fields.Many2one('hr.job', string='Job Position', required=True)
    subject = fields.Char(string='Subject', required=True)
    body = fields.Html(string='Body', required=True)
    employee_ids = fields.Many2many('hr.employee', string='Recipients', compute='_compute_employee_ids')
    recipient_count = fields.Integer(string='Recipients Count', compute='_compute_employee_ids')

    @api.depends('job_id')
    def _compute_employee_ids(self):
        for wizard in self:
            employees = wizard._get_recipient_employees()
            wizard.employee_ids = employees
            wizard.recipient_count = len(employees)

    def _get_recipient_employees(self):
        """Active internal employees with a work email, in the job's company (or the allowed companies)."""
        self.ensure_one()
        company_ids = self.job_id.company_id.ids or self.env.companies.ids
        employees = self.env['hr.employee'].sudo().search([
            ('work_email', '!=', False),
            ('company_id', 'in', company_ids),
            '|', ('user_id', '=', False), ('user_id.share', '=', False),
        ])
        # Keep one employee per email address
        seen = set()
        recipients = self.env['hr.employee']
        for employee in employees:
            email = employee.work_email.strip().lower()
            if email not in seen:
                seen.add(email)
                recipients |= employee
        return recipients

    def action_promote(self):
        self.ensure_one()
        employees = self._get_recipient_employees()
        if not employees:
            raise UserError(_("No internal employee with a work email was found to promote this job to."))

        email_from = self.env.user.email_formatted or self.env.company.email_formatted
        self.env['mail.mail'].sudo().create([{
            'subject': self.subject,
            'body_html': self.body,
            'email_from': email_from,
            'email_to': employee.work_email,
            'auto_delete': True,
        } for employee in employees])

        self.job_id.message_post(
            body=_("Job position promoted by email to %s employees.", len(employees)),
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("The job position has been promoted to %s employees.", len(employees)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
