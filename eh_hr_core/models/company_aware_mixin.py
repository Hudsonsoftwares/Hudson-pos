# -*- coding: utf-8 -*-
"""eh.hr.company.aware.mixin - strict multi-company safety.

OpenHRMS leaks null-company records across companies via global ir.rules with
``company_id = False``.  We refuse that pattern:

    * On create, ``company_id`` defaults to ``self.env.company`` and is required.
    * On write, attempts to change ``company_id`` to a company the user is not
      a member of are rejected - even by sudo, unless the explicit context
      key ``allow_cross_company`` is set AND audited.
    * The mixin emits an audit row for any cross-company elevation.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class HrCompanyAwareMixin(models.AbstractModel):
    _name = 'eh.hr.company.aware.mixin'
    _description = 'EH HR Platform - strict company-scope mixin'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
        help='Owning company. Cross-company access is forbidden by default.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        env_company = self.env.company
        for vals in vals_list:
            vals.setdefault('company_id', env_company.id)
            if vals['company_id'] not in self.env.user.company_ids.ids:
                self._refuse_cross_company(vals['company_id'])
        return super().create(vals_list)

    def write(self, vals):
        if 'company_id' in vals:
            new_id = vals['company_id']
            if new_id and new_id not in self.env.user.company_ids.ids:
                self._refuse_cross_company(new_id)
            # A genuine cross-company move is one where at least one record
            # actually changes company. A normal form save re-sends every
            # field, so company_id is in vals even when it is unchanged.
            changing = any(r.company_id.id != new_id for r in self)
            if new_id and changing and not self.env.context.get('allow_cross_company'):
                self._refuse_cross_company(new_id)
            # Audit only a real elevation, not a write that merely restates the
            # same company_id. Record every affected id, not just the first: a
            # multi-record cross-company write must be fully reconstructable.
            if changing:
                self.env['eh.hr.audit.log'].sudo().write_event(
                    model=self._name,
                    record_id=self.ids[0] if self else 0,
                    action='cross_company_write',
                    actor=self.env.user,
                    payload={'new_company_id': new_id, 'count': len(self),
                             'record_ids': self.ids},
                    company_id=new_id,
                )
        return super().write(vals)

    def _refuse_cross_company(self, company_id):
        raise AccessError(_(
            'Cross-company write rejected. User is not allowed to write '
            'records into company id=%s without an audited override.'
        ) % company_id)
