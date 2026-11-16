from odoo import models, fields

class HrJob(models.Model):
    _inherit = 'hr.job'

    referral_target = fields.Integer(string='Target')
    referral_recruiter_id = fields.Many2one('res.users', string='Recruiter')

    def action_dummy(self):
        return True

    def action_open_job_page(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/jobs/detail/{self.id}',
            'target': 'self',
        }

    def _get_job_url(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/jobs/detail/{self.id}"

    def action_send_email(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Job Opportunity by Mail',
            'res_model': 'eh.hr.referral.send.mail',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_subject': f'Job Opportunity: {self.name}',
                'default_body': f'Hello,<br/><br/>There is an amazing job opportunity for <b>{self.name}</b> in our company! Have a look: <a href="{self._get_job_url()}">Click here</a>',
                'default_job_id': self.id,
            }
        }

    def action_promote_job(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Promote Job Position',
            'res_model': 'eh.hr.referral.promote',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_job_id': self.id,
                'default_subject': f'We are hiring: {self.name}',
                'default_body': (
                    f'Hello,<br/><br/>We are looking for a new <b>{self.name}</b> '
                    f'({self.no_of_recruitment} open position(s)). '
                    f'Do you know someone who would be a great fit? Refer them and earn referral points!<br/><br/>'
                    f'<a href="{self._get_job_url()}">View the job offer</a>'
                ),
            }
        }

    def action_send_whatsapp(self):
        self.ensure_one()
        url = f"https://wa.me/?text=Check out this job opportunity: {self.name} at {self._get_job_url()}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_send_sms(self):
        self.ensure_one()
        url = f"sms:?body=Check out this job: {self.name} {self._get_job_url()}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_share_facebook(self):
        self.ensure_one()
        url = f"https://www.facebook.com/sharer/sharer.php?u={self._get_job_url()}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_share_linkedin(self):
        self.ensure_one()
        url = f"https://www.linkedin.com/sharing/share-offsite/?url={self._get_job_url()}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_share_x(self):
        self.ensure_one()
        url = f"https://twitter.com/intent/tweet?url={self._get_job_url()}&text=Check out this job: {self.name}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_copy_link(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Copy Job Link',
            'res_model': 'eh.hr.referral.copy.link',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_job_id': self.id}
        }
