# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    uae_is_uae_company = fields.Boolean(
        string='Is UAE Company',
        compute='_compute_uae_is_uae_company'
    )

    uae_employment_sector = fields.Selection(
        related='company_id.uae_employment_sector',
        readonly=False,
        string='UAE Employment Sector'
    )

    uae_emirate_id = fields.Many2one(
        related='company_id.uae_emirate_id',
        readonly=False,
        string='UAE Emirate'
    )

    uae_jurisdiction_type = fields.Selection(
        related='company_id.uae_jurisdiction_type',
        readonly=False,
        string='Jurisdiction Type'
    )

    uae_jurisdiction_id = fields.Many2one(
        related='company_id.uae_jurisdiction_id',
        readonly=False,
        string='UAE Jurisdiction',
        domain="[('emirate_id', '=', uae_emirate_id), ('jurisdiction_type', '=', uae_jurisdiction_type)]"
    )

    uae_labour_authority_id = fields.Many2one(
        related='company_id.uae_labour_authority_id',
        readonly=True,
        string='Labour Authority'
    )

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

    # UAE GPSSA Statutory Configuration Related Fields
    hds_ae_enable_gpssa = fields.Boolean(
        related='company_id.hds_ae_enable_gpssa',
        readonly=False,
        string="Enable GPSSA"
    )
    hds_ae_gpssa_employer_number = fields.Char(
        related='company_id.hds_ae_gpssa_employer_number',
        readonly=False,
        string="GPSSA Employer Number"
    )

    # UAE ADPF Statutory Configuration Related Fields
    hds_ae_enable_adpf = fields.Boolean(
        related='company_id.hds_ae_enable_adpf',
        readonly=False,
        string="Enable ADPF"
    )
    hds_ae_adpf_employer_number = fields.Char(
        related='company_id.hds_ae_adpf_employer_number',
        readonly=False,
        string="ADPF Employer Number"
    )

    uae_pension_scheme_ids = fields.Many2many(
        related='company_id.uae_pension_scheme_ids',
        readonly=False,
        string="Permitted UAE Pension Schemes"
    )

    @api.depends('company_id', 'company_id.country_id')
    def _compute_uae_is_uae_company(self):
        for record in self:
            company = record.company_id or self.env.company
            country = company.country_id if company else False
            code = (country.code or '').upper() if country else ''
            name = (country.name or '').strip().lower() if country else ''
            record.uae_is_uae_company = bool(
                code in ('AE', 'ARE') or 'emirates' in name or name == 'uae'
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_pension_company_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._sync_pension_company_values(vals)
        return super().write(vals)

    def _sync_pension_company_values(self, vals):
        """
        Synchronize GPSSA and ADPF fields to res.company simultaneously before ORM inverses trigger,
        ensuring that company-level @api.constrains validates both fields together.
        """
        sync_keys = {
            'hds_ae_enable_gpssa', 'hds_ae_gpssa_employer_number',
            'hds_ae_enable_adpf', 'hds_ae_adpf_employer_number',
        }
        if not any(k in vals for k in sync_keys):
            return

        company_id = vals.get('company_id')
        if company_id:
            company = self.env['res.company'].browse(company_id)
        elif self and hasattr(self, 'company_id') and self.company_id:
            company = self.company_id[0]
        else:
            company = self.env.company

        if not company:
            return

        pension_vals = {}
        # GPSSA sync
        if 'hds_ae_gpssa_employer_number' in vals:
            pension_vals['hds_ae_gpssa_employer_number'] = vals['hds_ae_gpssa_employer_number']
        elif hasattr(self, 'hds_ae_gpssa_employer_number') and self.hds_ae_gpssa_employer_number:
            pension_vals['hds_ae_gpssa_employer_number'] = self.hds_ae_gpssa_employer_number

        if 'hds_ae_enable_gpssa' in vals:
            pension_vals['hds_ae_enable_gpssa'] = vals['hds_ae_enable_gpssa']
        elif hasattr(self, 'hds_ae_enable_gpssa'):
            pension_vals['hds_ae_enable_gpssa'] = self.hds_ae_enable_gpssa

        # ADPF sync
        if 'hds_ae_adpf_employer_number' in vals:
            pension_vals['hds_ae_adpf_employer_number'] = vals['hds_ae_adpf_employer_number']
        elif hasattr(self, 'hds_ae_adpf_employer_number') and self.hds_ae_adpf_employer_number:
            pension_vals['hds_ae_adpf_employer_number'] = self.hds_ae_adpf_employer_number

        if 'hds_ae_enable_adpf' in vals:
            pension_vals['hds_ae_enable_adpf'] = vals['hds_ae_enable_adpf']
        elif hasattr(self, 'hds_ae_enable_adpf'):
            pension_vals['hds_ae_enable_adpf'] = self.hds_ae_enable_adpf

        if pension_vals:
            company.write(pension_vals)

