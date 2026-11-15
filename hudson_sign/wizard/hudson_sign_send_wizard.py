from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HudsonSignSendWizard(models.TransientModel):
    _name = 'hudson.sign.send.wizard'
    _description = 'Send Signature Request Wizard'

    template_id = fields.Many2one('hudson.sign.template', required=True, ondelete='cascade')
    subject = fields.Char('Subject', required=True, default='Signature Request')
    message = fields.Text('Message')
    cc = fields.Char('CC')
    valid_until = fields.Date('Valid Until')
    reminders = fields.Boolean('Reminders')
    reminder_days = fields.Integer('Reminder Days', default=7)
    hide_certificate_key = fields.Boolean('Hide Certificate Key')
    signing_order = fields.Boolean('Signing Order')
    is_sign_now = fields.Boolean('Is Sign Now')

    role_ids = fields.One2many('hudson.sign.send.wizard.role', 'wizard_id', string='Signers')
    has_multiple_roles = fields.Boolean(compute='_compute_has_multiple_roles')
    single_signer_id = fields.Many2one('res.partner', string='Signer', domain="[('email', '!=', False)]")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if res.get('is_sign_now'):
            partner_id = self.env.user.partner_id.id
            res['single_signer_id'] = partner_id
            for cmd in res.get('role_ids') or []:
                if isinstance(cmd, (list, tuple)) and len(cmd) == 3 and cmd[0] == 0:
                    cmd[2]['partner_id'] = partner_id
        return res

    @api.depends('role_ids')
    def _compute_has_multiple_roles(self):
        for wiz in self:
            wiz.has_multiple_roles = len(wiz.role_ids) > 1

    def _get_signers(self):
        """Ordered list of (role, partner)."""
        self.ensure_one()
        if self.has_multiple_roles:
            signers = [(line.role_id, line.partner_id) for line in self.role_ids.sorted('sequence')]
        else:
            signers = [(self.role_ids[:1].role_id, self.single_signer_id)]
        for role, partner in signers:
            if not partner:
                raise ValidationError(_("Please select a signer for all roles."))
            if not (partner.email or '').strip():
                raise ValidationError(_("The contact '%s' must have an email address configured.", partner.name))
        return signers

    def action_confirm(self):
        self.ensure_one()
        signers = self._get_signers()
        action = self.template_id._send_signature_request(signers, {
            'subject': self.subject,
            'message': self.message,
            'cc': self.cc,
            'is_sign_now': self.is_sign_now,
            'signing_order': self.signing_order,
            'reminders': self.reminders,
            'reminder_days': self.reminder_days,
            'valid_until': self.valid_until and fields.Date.to_string(self.valid_until),
            'hide_certificate_key': self.hide_certificate_key,
        })
        if self.is_sign_now and isinstance(action, dict) and action.get('type') == 'ir.actions.act_url':
            return action

        dms_file = self.template_id.dms_file_id
        if dms_file:
            next_action = {
                'type': 'ir.actions.act_window',
                'res_model': 'dms.file',
                'res_id': dms_file.id,
                'views': [[False, 'form']],
                'target': 'main',
            }
        else:
            next_action = self.env['ir.actions.act_window']._for_xml_id('hudson_sign.action_hudson_sign_request')
            next_action['target'] = 'main'

        recipient_names = ", ".join(filter(None, (partner.name for _role, partner in signers)))
        has_mail_server = bool(self.env['ir.mail_server'].sudo().search_count([]))
        if has_mail_server:
            title, notif_type = _("Request Sent"), 'success'
            message = _("Signature request sent successfully to %s.", recipient_names)
        else:
            title, notif_type = _("Request Created (SMTP Server Required)"), 'warning'
            message = _(
                "Signature request created for %s, but no Outgoing Mail Server is configured. "
                "Please set up an SMTP server in Settings > Technical > Outgoing Mail Servers to deliver emails.",
                recipient_names,
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notif_type,
                'sticky': not has_mail_server,
                'next': next_action,
            },
        }


class HudsonSignSendWizardRole(models.TransientModel):
    _name = 'hudson.sign.send.wizard.role'
    _description = 'Signature Request Wizard Signer'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('hudson.sign.send.wizard', required=True, ondelete='cascade')
    role_id = fields.Many2one('hudson.sign.template.role', string='Role', required=True)
    role_name = fields.Char(related='role_id.name', string='Role Name')
    partner_id = fields.Many2one('res.partner', string='Signer', domain="[('email', '!=', False)]")
    sequence = fields.Integer('Sequence')
