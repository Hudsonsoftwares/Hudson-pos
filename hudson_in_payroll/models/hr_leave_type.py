# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models

class HrLeaveType(models.Model):
    """
    Inherit Leave Type (hr.leave.type) to configure Leave Encashment eligibility.
    Adds a configurable checkbox: Include in Leave Encashment.
    """
    _inherit = 'hr.work.entry.type'

    include_in_leave_encashment = fields.Boolean(
        string="Include in Leave Encashment",
        default=False,
        help="If checked, this leave type is eligible for Leave Encashment calculations."
    )
