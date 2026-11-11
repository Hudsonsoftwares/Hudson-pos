# -*- coding: utf-8 -*-
"""
Migration: 19.0.1.0.2 — Remove stale overtime_multiplier / pay_overtime view arch.

Context:
  In version 1.0.1, the module stored overtime settings (overtime_multiplier,
  pay_overtime, overtime_hourly_rate, overtime_rate_manually_set) in:
    - res.config.settings (view: res.config.settings.view.form.inherit.hudson.attendance.payroll.link)
    - hr.version form (view: hr.version.view.form.inherit.rates)

  In 1.0.2 these fields were removed in favour of Standard Odoo 19 Overtime
  Rulesets (hr.attendance.overtime.line).  If the old arch_db is left in the
  database, the next module load raises a ParseError because the field no longer
  exists on the model.

  This pre-migration script rewrites those two views to a safe placeholder arch
  BEFORE Odoo tries to validate the combined inherited view.  The real clean arch
  is written by the data files immediately after migration.
"""

import logging

_logger = logging.getLogger(__name__)

# Safe minimal arch that replaces the stale overtime fields.
# The data XML will overwrite these with the real content after migration.
_SAFE_CONFIG_ARCH = """\
<xpath expr="//app[@name='hr_attendance']" position="inside">
    <block title="Attendance &amp; Payroll Connection"
           name="attendance_payroll_connection_setting_container">
        <setting string="Standard Working Days per Month"
                 help="Default monthly working days used for shortage deduction rate calculation.">
            <div class="content-group mt4">
                <field name="standard_working_days_per_month"/>
            </div>
        </setting>
        <setting string="Standard Hours per Day"
                 help="Default daily working hours used for shortage deduction rate calculation.">
            <div class="content-group mt4">
                <field name="standard_hours_per_day"/>
            </div>
        </setting>
    </block>
</xpath>"""

_SAFE_VERSION_ARCH = """\
<xpath expr="//group[@name='salary_breakdown']" position="after">
    <group string="Hourly Rate Configuration" name="hourly_rate_config">
        <field name="salary_calculation_type"/>
        <field name="pay_by_attendance" widget="boolean_toggle"/>
        <field name="hourly_rate" readonly="1"/>
        <field name="shortage_deduction_rate_per_hour"/>
        <field name="shortage_rate_manually_set" invisible="1"/>
        <button name="action_reset_to_computed_rates"
                string="Reset Shortage Rate"
                type="object"
                class="btn-secondary"
                invisible="not shortage_rate_manually_set"/>
    </group>
</xpath>"""

# (view_name, model, new_arch)
_STALE_VIEWS = [
    (
        'res.config.settings.view.form.inherit.hudson.attendance.payroll.link',
        'res.config.settings',
        _SAFE_CONFIG_ARCH,
    ),
    (
        'hr.version.view.form.inherit.rates',
        'hr.version',
        _SAFE_VERSION_ARCH,
    ),
]


def migrate(cr, version):
    """
    Odoo calls this automatically before loading data files during upgrade.
    Rewrites the arch_db of any stale overtime-referencing views so the
    module load no longer raises a ParseError.
    """
    if not version:
        # Fresh install — nothing to clean up.
        return

    import json

    for view_name, model, safe_arch in _STALE_VIEWS:
        cr.execute(
            "SELECT id, arch_db FROM ir_ui_view WHERE name = %s AND model = %s",
            (view_name, model),
        )
        row = cr.fetchone()
        if not row:
            _logger.debug(
                "pre_migrate 1.0.2: view '%s' not found, skipping.", view_name
            )
            continue

        view_id, arch_db = row

        # arch_db may be a dict (JSONB) or plain text depending on Odoo version.
        if isinstance(arch_db, dict):
            # Preserve existing translations but sanitise en_US.
            arch_db['en_US'] = safe_arch
            new_arch_db = json.dumps(arch_db)
        elif isinstance(arch_db, str):
            # Try to parse as JSON first (Odoo 16/17+ stores as JSON string).
            try:
                parsed = json.loads(arch_db)
                parsed['en_US'] = safe_arch
                new_arch_db = json.dumps(parsed)
            except (ValueError, TypeError):
                # Plain XML string — just replace directly.
                new_arch_db = safe_arch
        else:
            new_arch_db = safe_arch

        cr.execute(
            "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
            (new_arch_db, view_id),
        )
        _logger.info(
            "pre_migrate 1.0.2: cleaned stale OT fields from view '%s' (id=%s).",
            view_name,
            view_id,
        )
