# -*- coding: utf-8 -*-


def migrate(cr, version):
    # The auto-close inactivity is now measured from the last stage change: start from the
    # last known activity of existing tickets rather than from the upgrade date
    cr.execute("""
        UPDATE helpdesk_management_ticket
           SET date_last_stage_update = COALESCE(close_date, write_date, create_date)
    """)
