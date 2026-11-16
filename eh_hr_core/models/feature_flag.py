# -*- coding: utf-8 -*-
"""eh.hr.feature.flag - runtime feature gating.

Flags are evaluated by ``flag.is_enabled(code, env)`` and may be scoped by:
    * company,
    * user group,
    * percentage rollout (deterministic on user id),
    * date window.

Used by the framework to roll out engine versions safely.
"""
import hashlib
from odoo import api, fields, models


class HrFeatureFlag(models.Model):
    _name = 'eh.hr.feature.flag'
    _description = 'EH HR Platform - feature flag'

    code = fields.Char(required=True, index=True)
    description = fields.Text()
    enabled = fields.Boolean(default=False)
    company_ids = fields.Many2many('res.company', string='Companies (empty = all)')
    group_ids = fields.Many2many('res.groups', string='Groups (empty = all)')
    rollout_percent = fields.Integer(default=100, help='0-100. Deterministic on uid.')
    valid_from = fields.Datetime()
    valid_to = fields.Datetime()

    # Odoo 19 builds constraints from models.Constraint, not the
    # _sql_constraints list. Keep both so constraints hold on 16 to 19.
    if hasattr(models, 'Constraint'):
        _uniq_code = models.Constraint(
            'unique(code)',
            'Flag code must be unique.')
    else:
        _sql_constraints = [
            ('uniq_code', 'unique(code)', 'Flag code must be unique.'),
        ]

    @api.model
    def is_enabled(self, code, env=None):
        env = env or self.env
        flag = self.sudo().search([('code', '=', code)], limit=1)
        if not flag or not flag.enabled:
            return False
        now = fields.Datetime.now()
        if flag.valid_from and now < flag.valid_from:
            return False
        if flag.valid_to and now > flag.valid_to:
            return False
        user = env.user
        if flag.company_ids and env.company not in flag.company_ids:
            return False
        from odoo.addons.eh_hr_compat import user_groups
        if flag.group_ids and not (user_groups(user) & flag.group_ids):
            return False
        if flag.rollout_percent < 100:
            bucket = int(hashlib.md5(f'{code}:{user.id}'.encode()).hexdigest()[:8], 16) % 100
            if bucket >= flag.rollout_percent:
                return False
        return True
