# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HdsPtReportTile(models.Model):
    """
    Professional Tax (PT) Statutory Report Tile Model.
    Represents visual report cards displayed on the PT Statutory Reports Hub Dashboard.
    """
    _name = 'hds.pt.report.tile'
    _description = 'Professional Tax Report Hub Tile'
    _order = 'sequence, id'

    name = fields.Char(string="Report Name", required=True, translate=True)
    description = fields.Text(string="Description", translate=True)
    icon = fields.Char(string="FontAwesome Icon", default="fa-file-text-o")
    section = fields.Selection([
        ('filing', 'Registers & Statements'),
        ('summary', 'Summaries & Analytics'),
        ('analysis', 'Slab & Audit Analysis'),
        ('compliance', 'Compliance & Config Audit'),
    ], string="Category Section", default='summary', required=True)
    featured = fields.Boolean(string="Mandatory / Featured", default=False)
    report_type = fields.Selection([
        ('register', 'Professional Tax Register'),
        ('statement', 'Employee PT Statement'),
        ('monthly_summary', 'Monthly PT Summary'),
        ('state_summary', 'State-wise PT Summary'),
        ('company_summary', 'Company-wise PT Summary'),
        ('slab_utilization', 'Salary Slab Utilization Report'),
        ('override_month', 'PT Override Month Report'),
        ('exception', 'PT Exception Report'),
        ('compliance_audit', 'PT Compliance Audit Report'),
        ('reconciliation', 'PT Reconciliation Report'),
        ('revision_impact', 'Salary Revision Impact Report'),
        ('state_mapping', 'Employee State Mapping Report'),
        ('liability_summary', 'PT Liability Summary'),
        ('config_audit', 'Professional Tax Configuration Audit'),
    ], string="Report Target Type", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    country_code = fields.Char(string="Country Code", default="IN")

    def action_open_pt_report(self):
        self.ensure_one()
        action = self.env.ref('hudson_in_payroll.action_hds_pt_report_wizard').read()[0]
        action['target'] = 'new'
        action['context'] = {
            'default_report_type': self.report_type,
            'default_title': self.name,
        }
        return action
