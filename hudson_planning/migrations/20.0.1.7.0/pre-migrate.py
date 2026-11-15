# Part of Hudson Community. See LICENSE file for full copyright and licensing details.


def migrate(cr, version):
    """20.0.1.6.0 kept the hours of the sales orders to plan as shifts without
    dates: they become open shifts (see post-migrate), the dates are required
    again."""
    cr.execute("ALTER TABLE fs_planning_slot DROP CONSTRAINT IF EXISTS fs_planning_slot_dates_set_or_to_plan")
    cr.execute("DELETE FROM fs_planning_slot WHERE date_start IS NULL OR date_end IS NULL")
