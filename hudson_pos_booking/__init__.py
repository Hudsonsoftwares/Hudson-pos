# -*- coding: utf-8 -*-
from . import models
from . import controllers


def _post_init_hook(env):
    """Ensure Pre-Order Food preset and schedule exist safely on install without clobbering existing settings."""
    # 1. Ensure a resource calendar exists without overriding existing attendances
    cal = env.ref('pos_restaurant.pos_resource_preset', raise_if_not_found=False)
    if not cal:
        cal = env['resource.calendar'].search([('name', '=', 'Opening time')], limit=1)
    if not cal:
        cal = env['resource.calendar'].sudo().create({
            'name': 'Opening time',
            'company_id': env.company.id,
        })
    if cal and not cal.attendance_ids:
        attendances = []
        for day in range(7):
            attendances.append((0, 0, {
                'dayofweek': str(day),
                'hour_from': 11.0,
                'hour_to': 22.0,
                'day_period': 'full_day',
            }))
        cal.sudo().write({'attendance_ids': attendances})

    # 2. Dedicated Pre-Order Food preset (does NOT overwrite standard Takeout)
    preset = env['pos.preset'].search([('name', '=', 'Pre-Order Food')], limit=1)
    if not preset:
        preset_vals = {
            'name': 'Pre-Order Food',
            'color': 3,
            'identification': 'name',
            'use_timing': True,
            'slots_per_interval': 5,
            'interval_time': 20,
            'available_in_self': True,
            'service_at': 'counter',
            'resource_calendar_id': cal.id if cal else False,
        }
        mail_template = env.ref('pos_self_order.takeout_email_template', raise_if_not_found=False)
        if mail_template:
            preset_vals['mail_template_id'] = mail_template.id
        preset = env['pos.preset'].sudo().create(preset_vals)

    # 3. Attach preset to restaurant pos.config records that enable bookings
    pos_configs = env['pos.config'].sudo().search([('module_pos_restaurant', '=', True)])
    for cfg in pos_configs:
        if preset and preset not in cfg.available_preset_ids:
            cfg.write({'available_preset_ids': [(4, preset.id)]})

    # 4. Sync restaurant tables & configure Table Booking appointment type for website customer choice
    app_types = env['appointment.type'].sudo().search([('name', 'ilike', 'Table Booking')])
    for at in app_types:
        if at.assign_method != 'customer':
            at.write({'assign_method': 'customer'})
    tables = env['restaurant.table'].sudo().search([])
    tables._sync_appointment_resource()

    # 5. Ensure Online Prepaid POS payment method is configured for restaurant configs
    pos_configs._ensure_online_prepaid_payment_method()
