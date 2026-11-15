from odoo import Command, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hudson_sign_use_terms = fields.Boolean(
        string="Sign Default Terms & Conditions", config_parameter='hudson_sign.use_terms')
    hudson_sign_terms_type = fields.Selection(
        [('email', "Terms in Email"), ('web', "Terms as Web Page")], string="Terms & Conditions format",
        default='email', config_parameter='hudson_sign.terms_type')
    hudson_sign_terms = fields.Html(related='company_id.hudson_sign_terms', readonly=False)
    hudson_sign_manage_template_access = fields.Boolean(string="Manage template access")
    hudson_sign_email_otp = fields.Boolean(
        string="Email verification", config_parameter='hudson_sign.email_otp')
    hudson_sign_certificate_id = fields.Many2one(
        related='company_id.hudson_sign_certificate_id', readonly=False)

    @api.model
    def _hudson_sign_template_access_groups(self):
        return self.env.ref('base.group_user'), self.env.ref('hudson_sign.group_sign_template_access_open')

    @api.model
    def _hudson_sign_open_template_access(self):
        """Default: every internal user sees every template (no "Authorized Users")."""
        user_group, open_group = self._hudson_sign_template_access_groups()
        user_group.sudo().write({'implied_ids': [Command.link(open_group.id)]})

    @api.model
    def get_values(self):
        res = super().get_values()
        user_group, open_group = self._hudson_sign_template_access_groups()
        res['hudson_sign_manage_template_access'] = open_group not in user_group.implied_ids
        return res

    def set_values(self):
        super().set_values()
        user_group, open_group = self._hudson_sign_template_access_groups()
        managed = open_group not in user_group.implied_ids
        if self.hudson_sign_manage_template_access != managed:
            command = Command.unlink if self.hudson_sign_manage_template_access else Command.link
            user_group.sudo().write({'implied_ids': [command(open_group.id)]})
