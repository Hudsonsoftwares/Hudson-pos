# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class FieldServiceStopWizard(models.TransientModel):
    _name = 'field.service.stop.wizard'
    _description = 'Stop Timer Wizard'

    order_id = fields.Many2one(
        'field.service.order',
        string='Field Service Order',
        required=True,
    )
    start_time = fields.Datetime(string='Start Time', readonly=True)
    end_time = fields.Datetime(string='End Time', readonly=True)
    duration = fields.Float(
        string='Duration (Hours)',
        readonly=False,
        help='Elapsed time in hours. You can adjust this value.',
    )
    description = fields.Char(
        string='Work Description',
        help='Describe the work performed during this session.',
    )
    action_type = fields.Selection([
        ('pause', 'Pause'),
        ('stop', 'Stop & Complete'),
    ], string='Action', default='pause')

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        
        active_timer = self.env['field.service.active.timer'].search([
            ('order_id', '=', order.id),
            ('user_id', '=', self.env.user.id)
        ], limit=1)
        
        if not active_timer:
            raise UserError(_('Timer is not running for you!'))

        # Create timesheet entry
        self.env['field.service.timesheet'].create({
            'order_id': order.id,
            'user_id': self.env.user.id,
            'date': fields.Date.context_today(self),
            'description': self.description or _('Timer session'),
            'duration': self.duration,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'start_latitude': active_timer.current_latitude,
            'start_longitude': active_timer.current_longitude,
        })
        
        active_timer.unlink()

        # sudo: the timers of the other technicians are private to them
        remaining_timers = self.env['field.service.active.timer'].sudo().search_count([('order_id', '=', order.id)])
        
        if remaining_timers == 0:
            order.write({
                'state': 'paused',
                'last_paused_time': fields.Datetime.now(),
            })
        return True
