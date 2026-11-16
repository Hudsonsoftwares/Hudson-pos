from odoo import models, fields

class ReferralSendMail(models.TransientModel):
    _name = 'eh.hr.referral.send.mail'
    _description = 'Send Job Opportunity by Mail'

    email = fields.Char(string='Email', required=True)
    friend_name = fields.Char(string='Friend Name', required=True)
    subject = fields.Char(string='Subject', required=True, default="Job for you")
    body = fields.Html(string='Body', required=True, default="Hello,<br/><br/>There are some amazing job opportunities in my company! Have a look, they can be interesting for you:")
    job_id = fields.Many2one('hr.job', string='Job')

    def action_send_mail(self):
        self.ensure_one()
        
        # Create and send the email
        mail_values = {
            'subject': self.subject,
            'body_html': self.body,
            'email_to': self.email,
        }
        self.env['mail.mail'].sudo().create(mail_values).send()
        
        # Create an applicant record to increment the referral dashboard
        if self.job_id:
            self.env['hr.applicant'].sudo().create({
                'partner_name': self.friend_name,
                'email_from': self.email,
                'job_id': self.job_id.id,
                'ref_user_id': self.env.user.id,
            })
            
        # Return to the dashboard client action to prevent a blank screen
        return self.env.ref('eh_hr_referral.action_eh_hr_referral_dashboard_client').read()[0]
