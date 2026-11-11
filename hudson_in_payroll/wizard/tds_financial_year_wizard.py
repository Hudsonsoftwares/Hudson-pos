# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class TdsFinancialYearWizard(models.TransientModel):
    """
    Financial Year Roll-Over Wizard.
    Enables System Administrators to transition to the next Financial Year cleanly
    by cloning previous tax slabs, surcharge rates, and effective-dated rule parameters
    without modifying XML seed data or requiring developer code releases.
    """
    _name = 'tds.financial.year.wizard'
    _description = 'Financial Year Roll-Over Wizard'

    source_fy_id = fields.Many2one(
        'tds.financial.year',
        string="Source Financial Year",
        required=True,
        domain="[('active', '=', True)]",
        help="Target Financial Year to copy statutory configurations from."
    )
    name = fields.Char(
        string="New Tax Year Name",
        required=True,
        help="e.g. Tax Year: 2027-28"
    )
    code = fields.Char(
        string="Tax Year Code",
        required=True,
        help="e.g. 2027-2028"
    )
    assessment_year = fields.Char(
        string="Assessment Year",
        required=True,
        help="e.g. 2028-2029"
    )
    start_date = fields.Date(
        string="Start Date",
        required=True,
        help="Start date of new Financial Year (e.g. 2027-04-01)"
    )
    end_date = fields.Date(
        string="End Date",
        required=True,
        help="End date of new Financial Year (e.g. 2028-03-31)"
    )
    copy_tax_slabs = fields.Boolean(
        string="Copy Tax Slabs",
        default=True,
        help="Clone previous year's Old & New Regime tax slabs as editable templates."
    )
    copy_surcharge_slabs = fields.Boolean(
        string="Copy Surcharge Slabs",
        default=True,
        help="Clone previous year's surcharge slabs as editable templates."
    )
    set_as_company_default = fields.Boolean(
        string="Set as Company Default FY",
        default=True,
        help="Automatically update current company's default tax year to this new Financial Year."
    )
    close_previous_fy = fields.Boolean(
        string="Close Previous Financial Year",
        default=False,
        help="Mark the source Financial Year as closed to lock it against further modifications."
    )

    @api.model
    def default_get(self, fields_list):
        res = super(TdsFinancialYearWizard, self).default_get(fields_list)
        latest_fy = self.env['tds.financial.year'].search([('active', '=', True)], order='start_date desc', limit=1)
        if latest_fy:
            res['source_fy_id'] = latest_fy.id
            try:
                start_yr = latest_fy.start_date.year + 1
                end_yr = latest_fy.end_date.year + 1
                res['start_date'] = fields.Date.from_string(f"{start_yr}-04-01")
                res['end_date'] = fields.Date.from_string(f"{end_yr}-03-31")
                res['code'] = f"{start_yr}-{end_yr}"
                res['assessment_year'] = f"{end_yr}-{end_yr + 1}"
                res['name'] = f"Tax Year: {start_yr}-{str(end_yr)[-2:]}"
            except (AttributeError, ValueError, TypeError) as e:
                _logger.debug("Could not compute default next FY dates: %s", e)
        return res

    @api.onchange('source_fy_id')
    def _onchange_source_fy_id(self):
        if not self.source_fy_id:
            return

        source = self.source_fy_id
        try:
            start_yr = source.start_date.year + 1
            end_yr = source.end_date.year + 1
            self.start_date = fields.Date.from_string(f"{start_yr}-04-01")
            self.end_date = fields.Date.from_string(f"{end_yr}-03-31")
            self.code = f"{start_yr}-{end_yr}"
            self.assessment_year = f"{end_yr}-{end_yr + 1}"
            self.name = f"Tax Year: {start_yr}-{str(end_yr)[-2:]}"
        except (AttributeError, ValueError, TypeError) as e:
            _logger.debug("Could not compute onchange FY dates from source '%s': %s", getattr(source, 'name', 'N/A'), e)

    def action_create_financial_year(self):
        self.ensure_one()

        # Check uniqueness of code
        existing = self.env['tds.financial.year'].search([('code', '=', self.code)], limit=1)
        if existing:
            raise ValidationError(_(f"Financial Year with Code '{self.code}' already exists!"))

        # Create new FY. Slab lists are passed explicitly (empty) so tds.financial.year.default_get()
        # does not pre-fill them from the latest year; the copies below are the only source of slabs
        # (otherwise every slab is created twice and the overlap validation fails).
        new_fy = self.env['tds.financial.year'].create({
            'name': self.name,
            'code': self.code,
            'assessment_year': self.assessment_year,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'is_closed': False,
            'active': True,
            'tax_slab_ids': [],
            'surcharge_ids': [],
        })

        # Copy Tax Slabs
        if self.copy_tax_slabs and self.source_fy_id.tax_slab_ids:
            for slab in self.source_fy_id.tax_slab_ids:
                slab.copy({
                    'financial_year_id': new_fy.id,
                    'date_from': self.start_date,
                })

        # Copy Surcharge Slabs
        if self.copy_surcharge_slabs and self.source_fy_id.surcharge_ids:
            for surcharge in self.source_fy_id.surcharge_ids:
                surcharge.copy({
                    'financial_year_id': new_fy.id,
                    'date_from': self.start_date,
                })

        # Close previous FY if requested
        if self.close_previous_fy:
            self.source_fy_id.write({'is_closed': True})

        # Set as company default if requested
        if self.set_as_company_default:
            company = self.env.company
            if 'hds_in_default_tax_year' in company._fields:
                company.write({'hds_in_default_tax_year': new_fy.id})

        # Return action opening form view of newly created FY for admin review
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Financial Year Created'),
            'res_model': 'tds.financial.year',
            'res_id': new_fy.id,
            'view_mode': 'form',
            'target': 'current',
        }
