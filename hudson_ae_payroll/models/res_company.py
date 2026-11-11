# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    uae_employment_sector = fields.Selection([
        ('private', 'Private Sector'),
        ('government', 'Government Sector'),
    ], string='UAE Employment Sector',
        help='Identifies whether the company operates under the UAE private or government sector.')

    uae_emirate_id = fields.Many2one(
        'uae.emirate',
        string='UAE Emirate',
        help='The Emirate in which this entity is registered or primarily operates.'
    )

    uae_jurisdiction_type = fields.Selection([
        ('mainland', 'Mainland'),
        ('free_zone', 'Free Zone'),
    ], string='Jurisdiction Type',
        help='Mainland vs Free Zone jurisdiction classification.'
    )

    uae_jurisdiction_id = fields.Many2one(
        'uae.payroll.jurisdiction',
        string='UAE Jurisdiction',
        domain="[('emirate_id', '=', uae_emirate_id), ('jurisdiction_type', '=', uae_jurisdiction_type)]",
        help='Operating jurisdiction profile defining mainland or free zone rules.'
    )

    uae_labour_authority_id = fields.Many2one(
        'uae.labour.authority',
        string='Labour Authority',
        compute='_compute_uae_labour_authority_id',
        store=True,
        readonly=True,
        help='Governing regulatory body (e.g. MOHRE, Free Zone Authority) auto-resolved from the Jurisdiction.'
    )

    @api.depends('uae_jurisdiction_id', 'uae_jurisdiction_id.labour_authority_id')
    def _compute_uae_labour_authority_id(self):
        for company in self:
            if company.uae_jurisdiction_id and company.uae_jurisdiction_id.labour_authority_id:
                company.uae_labour_authority_id = company.uae_jurisdiction_id.labour_authority_id
            else:
                company.uae_labour_authority_id = False

    @api.onchange('uae_emirate_id')
    def _onchange_uae_emirate_id(self):
        if self.uae_jurisdiction_id:
            if not self.uae_emirate_id or self.uae_jurisdiction_id.emirate_id != self.uae_emirate_id:
                self.uae_jurisdiction_id = False
                self.uae_labour_authority_id = False

    @api.onchange('uae_jurisdiction_type')
    def _onchange_uae_jurisdiction_type(self):
        if self.uae_jurisdiction_id:
            if not self.uae_jurisdiction_type or self.uae_jurisdiction_id.jurisdiction_type != self.uae_jurisdiction_type:
                self.uae_jurisdiction_id = False
                self.uae_labour_authority_id = False

    @api.onchange('uae_jurisdiction_id')
    def _onchange_uae_jurisdiction_id(self):
        if self.uae_jurisdiction_id:
            self.uae_labour_authority_id = self.uae_jurisdiction_id.labour_authority_id
            if not self.uae_emirate_id and self.uae_jurisdiction_id.emirate_id:
                self.uae_emirate_id = self.uae_jurisdiction_id.emirate_id
            if not self.uae_jurisdiction_type and self.uae_jurisdiction_id.jurisdiction_type:
                self.uae_jurisdiction_type = self.uae_jurisdiction_id.jurisdiction_type
        else:
            self.uae_labour_authority_id = False

    @api.constrains('uae_jurisdiction_id', 'uae_emirate_id', 'uae_jurisdiction_type')
    def _check_uae_jurisdiction_consistency(self):
        for company in self:
            if company.uae_jurisdiction_id:
                jur = company.uae_jurisdiction_id
                if jur.emirate_id and jur.emirate_id != company.uae_emirate_id:
                    comp_emirate_name = company.uae_emirate_id.name if company.uae_emirate_id else _('None')
                    raise ValidationError(_(
                        "Selected Jurisdiction '%(jurisdiction)s' belongs to Emirate '%(jur_emirate)s', "
                        "which does not match company Emirate '%(company_emirate)s'."
                    ) % {
                        'jurisdiction': jur.name,
                        'jur_emirate': jur.emirate_id.name,
                        'company_emirate': comp_emirate_name,
                    })

                if jur.jurisdiction_type and jur.jurisdiction_type != company.uae_jurisdiction_type:
                    jur_type_label = dict(jur._fields['jurisdiction_type'].selection).get(jur.jurisdiction_type, jur.jurisdiction_type)
                    comp_type_label = dict(company._fields['uae_jurisdiction_type'].selection).get(company.uae_jurisdiction_type, company.uae_jurisdiction_type) or _('None')
                    raise ValidationError(_(
                        "Selected Jurisdiction '%(jurisdiction)s' has type '%(jur_type)s', "
                        "which does not match company Jurisdiction Type '%(company_type)s'."
                    ) % {
                        'jurisdiction': jur.name,
                        'jur_type': jur_type_label,
                        'company_type': comp_type_label,
                    })

    # UAE GPSSA Statutory Configuration Fields
    hds_ae_enable_gpssa = fields.Boolean(
        string="Enable GPSSA",
        default=False,
        help="Enable General Pension and Social Security Authority (GPSSA) statutory compliance for this company."
    )
    hds_ae_gpssa_employer_number = fields.Char(
        string="GPSSA Employer Number",
        help="Employer Registration / Establishment Code allotted by the General Pension and Social Security Authority (GPSSA)."
    )

    # UAE ADPF Statutory Configuration Fields
    hds_ae_enable_adpf = fields.Boolean(
        string="Enable ADPF",
        default=False,
        help="Enable Abu Dhabi Pension Fund (ADPF) statutory compliance for this company."
    )
    hds_ae_adpf_employer_number = fields.Char(
        string="ADPF Employer Number",
        help="Employer Registration / Establishment Code allotted by the Abu Dhabi Pension Fund (ADPF)."
    )

    # UAE Pension Scheme Availability (Enables concurrent Legacy vs New Law cohorts)
    uae_pension_scheme_ids = fields.Many2many(
        'uae.pension.scheme',
        'res_company_uae_pension_scheme_rel',
        'company_id',
        'scheme_id',
        string="Permitted UAE Pension Schemes",
        help="Defines which pension schemes (Legacy vs New Law) are enabled for this company, allowing coexisting cohorts."
    )

    @api.constrains('hds_ae_enable_gpssa', 'hds_ae_gpssa_employer_number')
    def _check_hds_ae_gpssa_configuration(self):
        for company in self:
            if company.hds_ae_enable_gpssa and not (company.hds_ae_gpssa_employer_number or '').strip():
                raise ValidationError(_(
                    "GPSSA Employer Number is required when GPSSA is enabled for company '%s'."
                ) % company.name)

    @api.constrains('hds_ae_enable_adpf', 'hds_ae_adpf_employer_number')
    def _check_hds_ae_adpf_configuration(self):
        for company in self:
            if company.hds_ae_enable_adpf and not (company.hds_ae_adpf_employer_number or '').strip():
                raise ValidationError(_(
                    "ADPF Employer Number is required when ADPF is enabled for company '%s'."
                ) % company.name)

    def is_pension_authority_enabled(self, authority):
        """
        Check if a given UAE pension authority is enabled for this company.
        :param authority: uae.pension.authority record or string code
        :return: bool
        """
        self.ensure_one()
        if not authority:
            return False
        code = (authority.code if hasattr(authority, 'code') else str(authority)).upper()
        if code == 'GPSSA':
            return bool(self.hds_ae_enable_gpssa)
        elif code == 'ADPF':
            return bool(self.hds_ae_enable_adpf)
        return False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('hds_ae_gpssa_employer_number'):
                vals['hds_ae_gpssa_employer_number'] = vals['hds_ae_gpssa_employer_number'].strip()
            if vals.get('hds_ae_adpf_employer_number'):
                vals['hds_ae_adpf_employer_number'] = vals['hds_ae_adpf_employer_number'].strip()
            if vals.get('uae_jurisdiction_id'):
                jur = self.env['uae.payroll.jurisdiction'].browse(vals['uae_jurisdiction_id'])
                if jur.exists():
                    if 'uae_emirate_id' not in vals and jur.emirate_id:
                        vals['uae_emirate_id'] = jur.emirate_id.id
                    if 'uae_jurisdiction_type' not in vals and jur.jurisdiction_type:
                        vals['uae_jurisdiction_type'] = jur.jurisdiction_type
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('hds_ae_gpssa_employer_number'):
            vals['hds_ae_gpssa_employer_number'] = vals['hds_ae_gpssa_employer_number'].strip()
        if vals.get('hds_ae_adpf_employer_number'):
            vals['hds_ae_adpf_employer_number'] = vals['hds_ae_adpf_employer_number'].strip()
        if vals.get('uae_jurisdiction_id'):
            jur = self.env['uae.payroll.jurisdiction'].browse(vals['uae_jurisdiction_id'])
            if jur.exists():
                if 'uae_emirate_id' not in vals and jur.emirate_id:
                    vals['uae_emirate_id'] = jur.emirate_id.id
                if 'uae_jurisdiction_type' not in vals and jur.jurisdiction_type:
                    vals['uae_jurisdiction_type'] = jur.jurisdiction_type

        # Track previous emirates before updating to cascade to employees
        old_emirates = {c.id: c.uae_emirate_id.id for c in self} if 'uae_emirate_id' in vals else {}
        res = super().write(vals)

        if 'uae_emirate_id' in vals:
            for company in self:
                new_emirate = company.uae_emirate_id
                old_emirate_id = old_emirates.get(company.id)
                if new_emirate and new_emirate.id != old_emirate_id:
                    # Update employees belonging to this company who defaulted from company
                    domain = [('company_id', '=', company.id)]
                    if old_emirate_id:
                        domain += ['|', ('uae_emirate_id', '=', old_emirate_id), ('uae_emirate_id', '=', False)]
                    else:
                        domain += [('uae_emirate_id', '=', False)]
                    employees = self.env['hr.employee'].search(domain)
                    for emp in employees:
                        # If employee has work location with an emirate, work location takes priority
                        if emp.work_location_id and hasattr(emp.work_location_id, 'uae_emirate_id') and emp.work_location_id.uae_emirate_id:
                            emp.uae_emirate_id = emp.work_location_id.uae_emirate_id
                        else:
                            emp.uae_emirate_id = new_emirate
        return res

