from odoo import models

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def action_open_referral_dashboard(self):
        self.ensure_one()
        return self.env['ir.actions.client']._for_xml_id('eh_hr_referral.action_eh_hr_referral_dashboard_client')
