# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models


class BankProxy:
    """Compatibility proxy for Odoo 20 where res.bank was removed and bank_id is no longer on res.partner.bank."""
    def __init__(self, record):
        self._record = record

    @property
    def name(self):
        return getattr(self._record, 'bank_name', '') or ''

    @property
    def bic(self):
        return getattr(self._record, 'bank_bic', '') or ''

    def __bool__(self):
        return bool(getattr(self._record, 'bank_name', False) or getattr(self._record, 'bank_bic', False))

    def __repr__(self):
        return f"<BankProxy name={self.name!r} bic={self.bic!r}>"


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    acc_number = fields.Char(
        related='account_number',
        string='Account Number',
        readonly=False,
    )

    @property
    def bank_id(self):
        """Provide backwards compatibility for code/templates accessing bank_acc.bank_id."""
        return BankProxy(self)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'acc_number' in vals and not vals.get('account_number'):
                vals['account_number'] = vals['acc_number']
        return super().create(vals_list)

    @api.model
    def name_create(self, name):
        """Allows direct account number entry and creation from Many2one dropdowns."""
        partner_id = self.env.context.get('default_partner_id')
        company_id = self.env.context.get('default_company_id')
        if not partner_id and company_id:
            company = self.env['res.company'].browse(company_id)
            partner_id = company.partner_id.id
        if not partner_id:
            partner_id = self.env.company.partner_id.id

        clean_name = name.strip()
        domain = [('partner_id', '=', partner_id)]
        if 'acc_number' in self._fields:
            domain.append(('acc_number', '=ilike', clean_name))
        elif 'account_number' in self._fields:
            domain.append(('account_number', '=ilike', clean_name))
        existing = self.search(domain, limit=1)
        if existing:
            return existing.id, existing.display_name

        vals = {
            'partner_id': partner_id,
        }
        if 'acc_number' in self._fields:
            vals['acc_number'] = clean_name
        elif 'account_number' in self._fields:
            vals['account_number'] = clean_name
        if company_id:
            vals['company_id'] = company_id
        record = self.create(vals)
        return record.id, record.display_name
