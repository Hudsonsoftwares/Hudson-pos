# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Let this upgrade reload the celebration wish emails (noupdate data) so they
    show the guest's chosen life event (Birthday, Wedding, ...) instead of the
    appointment type name. post-migrate puts noupdate back."""
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = FALSE
         WHERE module = 'hudson_pos_booking'
           AND name IN ('email_template_celebration_advance', 'email_template_celebration_day')
    """)
