# pyrefly: ignore [missing-import]
from odoo import models, fields, api
import uuid

class AppointmentInvite(models.Model):
    _name = 'appointment.invite'
    _description = 'Appointment Invite'

    name = fields.Char('Invite Reference', required=True, default='New')
    appointment_type_ids = fields.Many2many('appointment.type', string='Appointment Types')
    
    assign_method = fields.Selection([
        ('any', 'Any Resource'),
        ('specific', 'Specific Resources')
    ], string='Assign to', default='any')
    
    staff_user_ids = fields.Many2many('res.users', string='Specific Staff')
    resource_ids = fields.Many2many('appointment.resource', string='Specific Resources')
    
    access_token = fields.Char('Access Token', default=lambda s: str(uuid.uuid4()), required=True, readonly=True)
    short_code = fields.Char('Short Code', copy=False)
    book_url = fields.Char('Link', compute='_compute_book_url')
    appointment_count = fields.Integer('# Bookings', default=0)

    @api.depends('short_code', 'access_token', 'appointment_type_ids', 'assign_method', 'staff_user_ids', 'resource_ids')
    def _compute_book_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
        for invite in self:
            url = ""
            if len(invite.appointment_type_ids) > 0:
                apt_id = invite.appointment_type_ids[0]._origin.id or invite.appointment_type_ids[0].id
                url = f"{base_url}/appointment/{apt_id}?invite_token={invite.access_token}"
            else:
                code = invite.short_code or invite.access_token
                url = f"{base_url}/book/{code}"
                
            if invite.assign_method == 'specific':
                params = []
                if invite.staff_user_ids:
                    params.append(f"staff_ids={','.join(map(str, invite.staff_user_ids.ids))}")
                if invite.resource_ids:
                    params.append(f"resource_ids={','.join(map(str, invite.resource_ids.ids))}")
                if params:
                    url = f"{url}?{'&'.join(params)}"
            
            invite.book_url = url

    def action_copy_and_close(self):
        # The frontend client action handles the actual copying to clipboard
        return {
            'type': 'ir.actions.client',
            'tag': 'appointment.action_copy_close',
            'params': {
                'url': self.book_url,
                'close': True,
            }
        }

    def action_copy_link(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'appointment.action_copy_close',
            'params': {
                'url': self.book_url,
                'close': False,
            }
        }
