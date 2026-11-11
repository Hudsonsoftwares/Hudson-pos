# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models


class QualityReason(models.Model):
    _name = "quality.reason"
    _description = "Root Cause for Quality Failure"

    name = fields.Char('Name', required=True, translate=True)
