from . import models


def post_init_hook(env):
    _ensure_work_entry_types_and_rules(env)
    # Colorize public/bank holiday leave types for visual clarity
    leave_types = env['hr.work.entry.type'].sudo().search([])
    for lt in leave_types:
        name = lt.name or ''
        if any(keyword in name.lower() for keyword in ['public', 'holiday', 'bank', 'global']):
            lt.color = 2

    # Retroactively fix any existing contracts with 0.0 shortage deduction rate.
    # Overtime rates are now managed by Standard Odoo 19 Overtime Rulesets —
    # no retroactive fix needed for OT rates.
    contracts = env['hr.version'].sudo().search([])
    for contract in contracts:
        if contract.shortage_deduction_rate_per_hour == 0.0:
            days = contract.standard_working_days_per_month or 26.0
            hours = contract.standard_hours_per_day or 8.0
            divisor = days * hours
            computed_hourly = contract.wage / divisor if divisor else 0.0
            if computed_hourly > 0.0:
                contract.write({
                    'shortage_deduction_rate_per_hour': computed_hourly,
                    'shortage_rate_manually_set': False,
                })


def _ensure_work_entry_types_and_rules(env):
    """
    Ensures that WORK OT and WORK HOLIDAY work entry types and their
    corresponding overtime time rules exist out of the box in fresh databases.
    """
    WET = env['hr.work.entry.type'].sudo()
    TimeRule = env['hr.time.rule'].sudo()

    # 1. Ensure WORK OT
    work_ot = WET.search([('name', '=ilike', 'WORK OT')], limit=1)
    if not work_ot:
        std_work = (
            WET.search([('name', '=ilike', 'HUDSON WORK')], limit=1)
            or WET.search([('code', '=', '002.00'), ('country_id', '=', False)], limit=1)
            or WET.search([('code', '=', '002.00')], limit=1)
        )
        if std_work:
            std_work.write({'name': 'WORK OT'})
            work_ot = std_work
        else:
            try:
                work_ot = WET.create({
                    'name': 'WORK OT',
                    'code': '002.00',
                    'color': 0,
                })
            except Exception:
                work_ot = WET.create({
                    'name': 'WORK OT',
                    'code': 'WORK_OT',
                    'color': 0,
                })

    # 2. Ensure WORK HOLIDAY (must have a unique code 'WORK_HOLIDAY' so it never conflicts with '002.00')
    work_hol = WET.search([('name', '=ilike', 'WORK HOLIDAY')], limit=1)
    if not work_hol:
        std_hol = (
            WET.search([('name', 'ilike', 'HUDSON WORK HOLIDAY')], limit=1)
            or WET.search([('code', '=', 'WORK_HOLIDAY')], limit=1)
        )
        if std_hol:
            std_hol.write({'name': 'WORK HOLIDAY', 'color': 2})
            work_hol = std_hol
        else:
            work_hol = WET.create({
                'name': 'WORK HOLIDAY',
                'code': 'WORK_HOLIDAY',
                'color': 2,
            })

    # 3. Find Overtime Work Entry Types
    ot_150 = WET.search([('amount_rate', '=', 1.5)], limit=1) or WET.search([('name', 'ilike', '150%')], limit=1)
    ot_200 = WET.search([('amount_rate', '=', 2.0)], limit=1) or WET.search([('name', 'ilike', '200%')], limit=1)

    # 4. Ensure Mon-Fri Overtime Rule
    rule_work = TimeRule.search([('apply_monday', '=', True), ('apply_saturday', '=', False), ('apply_sunday', '=', False)], limit=1)
    if not rule_work:
        TimeRule.create({
            'name': 'Employee Schedule Rule',
            'working_hours_mode': 'schedule_day',
            'calendar_source': 'employee',
            'quantity_period': 'day',
            'apply_monday': True,
            'apply_tuesday': True,
            'apply_wednesday': True,
            'apply_thursday': True,
            'apply_friday': True,
            'apply_saturday': False,
            'apply_sunday': False,
            'apply_on_public_holidays': False,
            'condition_work_entry_type_ids': [(4, work_ot.id)],
            'work_entry_type_id': ot_150.id if ot_150 else False,
            'amount_rate': 1.5,
        })
    else:
        if work_ot.id not in rule_work.condition_work_entry_type_ids.ids:
            rule_work.write({'condition_work_entry_type_ids': [(4, work_ot.id)]})

    # 5. Ensure Sat, Sun, Public Holidays Overtime Rule
    rule_hol = TimeRule.search([('apply_saturday', '=', True), ('apply_sunday', '=', True)], limit=1)
    if not rule_hol:
        TimeRule.create({
            'name': 'HOLIDAY WORKING',
            'working_hours_mode': 'schedule_day',
            'calendar_source': 'employee',
            'quantity_period': 'day',
            'apply_monday': False,
            'apply_tuesday': False,
            'apply_wednesday': False,
            'apply_thursday': False,
            'apply_friday': False,
            'apply_saturday': True,
            'apply_sunday': True,
            'apply_on_public_holidays': True,
            'condition_work_entry_type_ids': [(4, work_hol.id)],
            'work_entry_type_id': ot_200.id if ot_200 else (ot_150.id if ot_150 else False),
            'amount_rate': 2.0,
        })
    else:
        if work_hol.id not in rule_hol.condition_work_entry_type_ids.ids:
            rule_hol.write({'condition_work_entry_type_ids': [(4, work_hol.id)]})
