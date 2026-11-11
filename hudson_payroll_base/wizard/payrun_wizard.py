# -*- coding: utf-8 -*-
import calendar
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError


class HudsonPayrollPayrunWizard(models.TransientModel):
    _name = 'hudson.payroll.payrun.wizard'
    _description = 'New Pay Run Wizard'

    @api.model
    def _domain_company_id(self):
        return [('id', 'in', self.env.companies.ids)]

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        domain=_domain_company_id,
        help="Select the company entity responsible for this pay run batch."
    )
    name = fields.Char(
        string='Pay Run Title',
        help="Leave blank to automatically name based on period and structure."
    )
    date_start = fields.Date(
        string='Period From',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_end = fields.Date(
        string='Period To',
        required=True,
        default=lambda self: (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()
    )

    @api.onchange('date_start')
    def _onchange_date_start(self):
        if self.date_start:
            last_day = calendar.monthrange(self.date_start.year, self.date_start.month)[1]
            self.date_end = self.date_start.replace(day=last_day)

    employee_type_ids = fields.Many2many(
        'hr.employee.type',
        string='Employee Types',
        help="Select specific employee types. Leave empty for all employee types."
    )
    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Pay Structure',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Select a structure. Leave empty to use employee default structure."
    )
    company_partner_id = fields.Many2one(
        'res.partner',
        string='Company Partner',
        related='company_id.partner_id',
        readonly=True
    )
    company_bank_id = fields.Many2one(
        'res.partner.bank',
        string='Company Bank Account',
        domain="['|', ('partner_id', '=', company_partner_id), ('company_id', '=', company_id)]",
        help="Disbursing bank account of the company for this pay run."
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company_id = res.get('company_id') or self.env.company.id
        if company_id:
            company = self.env['res.company'].browse(company_id)
            if 'company_bank_id' in (fields_list or []) and not res.get('company_bank_id'):
                bank_acc = company.partner_id.bank_ids and company.partner_id.bank_ids.filtered(
                    lambda b: not b.company_id or b.company_id == company
                )[:1] or False
                if not bank_acc:
                    bank_acc = self.env['res.partner.bank'].search([
                        '|', ('partner_id', '=', company.partner_id.id), ('company_id', '=', company.id),
                    ], limit=1)
                if bank_acc:
                    res['company_bank_id'] = bank_acc.id
            if 'struct_id' in (fields_list or []) and not res.get('struct_id'):
                domain = [('name', 'ilike', 'Regular Pay')]
                if company_id:
                    domain = ['|', ('company_id', '=', False), ('company_id', '=', company_id)] + domain
                struct = self.env['hr.payroll.structure'].search(domain, limit=1)
                if not struct and company_id:
                    struct = self.env['hr.payroll.structure'].search([
                        '|', ('company_id', '=', False), ('company_id', '=', company_id)
                    ], limit=1)
                if struct:
                    res['struct_id'] = struct.id
        return res

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            if self.struct_id and self.struct_id.company_id and self.struct_id.company_id != self.company_id:
                self.struct_id = False
            if self.company_bank_id and self.company_bank_id.company_id and self.company_bank_id.company_id != self.company_id:
                self.company_bank_id = False
            if not self.company_bank_id:
                bank_acc = self.company_id.partner_id.bank_ids and self.company_id.partner_id.bank_ids.filtered(
                    lambda b: not b.company_id or b.company_id == self.company_id
                )[:1] or False
                if not bank_acc:
                    bank_acc = self.env['res.partner.bank'].search([
                        '|', ('partner_id', '=', self.company_id.partner_id.id), ('company_id', '=', self.company_id.id),
                    ], limit=1)
                self.company_bank_id = bank_acc

    def action_confirm_and_generate(self):
        """Create Pay Run record and open the Select Employees dialog for the user to choose employees."""
        self.ensure_one()
        if self.date_start > self.date_end:
            raise UserError(_("Date From must be earlier than or equal to Date To."))

        run_name = self.name
        if not run_name:
            struct_name = self.struct_id.name if self.struct_id else _("Regular Pay")
            run_name = "%s (%s)" % (
                self.date_start.strftime("%b %Y"),
                self.company_id.country_id.code if self.company_id.country_id else self.company_id.name[:2].upper()
            )

        # Resolve company bank account
        bank_acc = self.company_bank_id
        if not bank_acc:
            company = self.company_id
            bank_acc = company.partner_id.bank_ids and company.partner_id.bank_ids.filtered(
                lambda b: not b.company_id or b.company_id == company
            )[:1] or False
            if not bank_acc:
                bank_acc = self.env['res.partner.bank'].search([
                    '|', ('partner_id', '=', company.partner_id.id), ('company_id', '=', company.id),
                ], limit=1)

        payrun_vals = {
            'name': run_name,
            'company_id': self.company_id.id,
            'company_bank_id': bank_acc.id if bank_acc else False,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'employee_type_ids': [(6, 0, self.employee_type_ids.ids)],
            'struct_id': self.struct_id.id if self.struct_id else False,
            'state': 'draft',
            'active_stage': 'employees',
        }

        payrun = self.env['hr.payslip.run'].with_company(self.company_id).create(payrun_vals)

        # Open the "Select Employees" dialog
        return {
            'name': _('Select Employees'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.employees',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'active_id': payrun.id,
                'active_ids': [payrun.id],
                'active_model': 'hr.payslip.run',
                'default_payslip_run_id': payrun.id,
            },
        }
