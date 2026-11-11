# -*- coding: utf-8 -*-
from odoo import api, fields, models
from random import randint

class HelpdeskManagementTag(models.Model):
    _name = 'helpdesk.management.tag'
    _description = 'Helpdesk Tag'

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(string='Tag Name', required=True, translate=True)
    color = fields.Integer(string='Color Index', default=_get_default_color)
    active = fields.Boolean(default=True)
    user_ids = fields.Many2many('res.users', string='Assigned Users')

class HelpdeskManagementCategory(models.Model):
    _name = 'helpdesk.management.category'
    _description = 'Helpdesk Category'
    _order = 'sequence, id'

    name = fields.Char(string='Category Name', required=True, translate=True)
    parent_id = fields.Many2one('helpdesk.management.category', string='Parent Category', index=True)
    child_ids = fields.One2many('helpdesk.management.category', 'parent_id', string='Subcategories')
    team_id = fields.Many2one('helpdesk.management.team', string='Helpdesk Team')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

class HelpdeskManagementSource(models.Model):
    _name = 'helpdesk.management.source'
    _description = 'Helpdesk Source'

    name = fields.Char(string='Source Name', required=True, translate=True)
    active = fields.Boolean(default=True)
