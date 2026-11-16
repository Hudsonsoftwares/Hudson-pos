from odoo import models, fields

class ReferralCopyLink(models.TransientModel):
    _name = 'eh.hr.referral.copy.link'
    _description = 'Copy Job Link'

    job_id = fields.Many2one('hr.job', string='Job Position', required=True)
    job_url = fields.Char(string='Job Link', compute='_compute_job_url')

    def _compute_job_url(self):
        for record in self:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            record.job_url = f"{base_url}/jobs/detail/{record.job_id.id}"
