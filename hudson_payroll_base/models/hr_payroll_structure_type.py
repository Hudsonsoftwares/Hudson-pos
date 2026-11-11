# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayrollStructureType(models.Model):
    """Payroll Structure Type allows categorizing structures by employment type / country."""
    _name = 'hr.payroll.structure.type'
    _description = 'Salary Structure Type'

    name = fields.Char(string='Structure Type', required=True, translate=True)
    default_resource_calendar_id = fields.Many2one(
        'resource.calendar',
        string='Working Hours',
        default=lambda self: self.env.company.resource_calendar_id
    )
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        default=lambda self: self.env['hr.payroll.structure']._default_country_id(),
        domain=lambda self: self.env['hr.payroll.structure']._get_payroll_country_domain(),
        help="Country for which this structure type applies."
    )
    wage_type = fields.Selection([
        ('monthly', 'Fixed Wage'),
        ('hourly', 'Hourly Wage'),
    ], string='Wage Type', default='monthly', required=True)
    struct_type_code = fields.Char(string='Code')
    schedule_pay = fields.Selection([
        ('monthly', 'month'),
        ('quarterly', 'quarter'),
        ('semi-annually', 'half-year'),
        ('annually', 'year'),
        ('weekly', 'week'),
        ('bi-weekly', 'bi-week'),
        ('bi-monthly', 'bi-month'),
    ], string='Scheduled Pay', default='monthly', required=True)
    time_type = fields.Selection([
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('intern', 'Internship / Stipend'),
    ], string='Time Type', default='full_time')
    default_struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Pay Structure',
        help="Default regular pay structure applied to contracts of this structure type."
    )
    default_work_entry_type_id = fields.Many2one(
        'hr.work.entry.type',
        string='Time Type',
        default=lambda self: self.env.ref('hr_work_entry.work_entry_type_attendance', raise_if_not_found=False)
                or self.env['hr.work.entry.type'].search([('code', '=', 'WORK100')], limit=1),
        domain="['|', ('country_id', '=', False), ('country_id', '=', country_id)]",
        help="Work entry type representing attendance and normal working time."
    )
    struct_ids = fields.One2many(
        'hr.payroll.structure',
        'type_id',
        string='Related Structures',
        help="All salary structures belonging to this structure type."
    )
    struct_count = fields.Integer(
        string='Structures Count',
        compute='_compute_struct_count'
    )

    def _compute_struct_count(self):
        for rec in self:
            rec.struct_count = len(rec.struct_ids)

    def action_open_structures(self):
        self.ensure_one()
        return {
            'name': 'Salary Structures',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payroll.structure',
            'view_mode': 'list,form',
            'domain': [('type_id', '=', self.id)],
            'context': {
                'default_type_id': self.id,
                'default_country_id': self.country_id.id if self.country_id else False
            },
        }
