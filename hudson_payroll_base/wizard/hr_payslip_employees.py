# -*- coding: utf-8 -*-
import json
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError


class HrPayslipEmployees(models.TransientModel):
    """Wizard to select employees for a payslip batch. Matches the Odoo Online 'Select Employees' dialog."""
    _name = 'hr.payslip.employees'
    _description = 'Generate Payslips for all selected employees'

    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Pay Run Batch',
        default=lambda self: self.env.context.get('active_id') if self.env.context.get('active_model') == 'hr.payslip.run' else False,
        help="Active pay run batch."
    )
    existing_employee_ids = fields.Many2many(
        'hr.employee',
        string='Existing Employees in Pay Run',
        compute='_compute_existing_employee_ids',
        help="Employees who already have a payslip in this pay run batch."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        readonly=True,
        help="Company associated with the active pay run batch."
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        'hr_payslip_employees_rel',
        'wizard_id',
        'employee_id',
        string='Employees',
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), ('id', 'not in', existing_employee_ids)]"
    )
    selected_employee_ids_json = fields.Char(
        string='Selected Employee IDs JSON',
        help="JSON array of employee IDs selected via checkboxes."
    )

    @api.depends('payslip_run_id', 'payslip_run_id.slip_ids')
    def _compute_existing_employee_ids(self):
        for wiz in self:
            if wiz.payslip_run_id:
                wiz.existing_employee_ids = wiz.payslip_run_id.slip_ids.mapped('employee_id')
            else:
                active_id = self.env.context.get('active_id')
                if active_id and self.env.context.get('active_model') == 'hr.payslip.run':
                    run = self.env['hr.payslip.run'].browse(active_id)
                    wiz.existing_employee_ids = run.slip_ids.mapped('employee_id')
                else:
                    wiz.existing_employee_ids = False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id and self.env.context.get('active_model') == 'hr.payslip.run':
            run = self.env['hr.payslip.run'].browse(active_id)
            res['payslip_run_id'] = run.id
            if 'company_id' in fields_list or not fields_list:
                res['company_id'] = run.company_id.id
            existing_emp_ids = run.slip_ids.mapped('employee_id').ids
            res['existing_employee_ids'] = [(6, 0, existing_emp_ids)]

            # Auto-select all eligible employees based on the pay run's employee_type_ids filter
            domain = [
                ('company_id', '=', run.company_id.id),
                ('active', '=', True),
                ('id', 'not in', existing_emp_ids),
            ]
            if run.employee_type_ids:
                reg_type = self.env['hr.employee.type'].search([('code', '=', 'EMP')], limit=1)
                if reg_type and reg_type.id in run.employee_type_ids.ids:
                    domain.append('|')
                    domain.append(('employee_type_id', 'in', run.employee_type_ids.ids))
                    domain.append(('employee_type_id', '=', False))
                else:
                    domain.append(('employee_type_id', 'in', run.employee_type_ids.ids))
            eligible_employees = self.env['hr.employee'].search(domain)
            if 'employee_ids' in fields_list or not fields_list:
                res['employee_ids'] = [(6, 0, eligible_employees.ids)]
            # BY DEFAULT UNSELECTED: Start with empty selection matching Screenshot 2
            res['selected_employee_ids_json'] = json.dumps([])
        return res

    def _get_selected_employees(self):
        """Employees ticked in the selection table (stored as a JSON list of ids)."""
        self.ensure_one()
        try:
            sel_ids = json.loads(self.selected_employee_ids_json or '[]')
        except (TypeError, ValueError):
            sel_ids = []
        if not isinstance(sel_ids, list):
            return self.env['hr.employee']
        sel_ids = [i for i in sel_ids if isinstance(i, int)]
        return self.env['hr.employee'].browse(sel_ids).exists()

    def action_select(self):
        """Generate payslips for the selected employees and open the Pay Run form."""
        payslip_run_id = self.env.context.get('active_id') or (self.payslip_run_id.id if self.payslip_run_id else False)
        if not payslip_run_id:
            raise UserError(_("No active payrun batch found."))

        run = self.env['hr.payslip.run'].browse(payslip_run_id)
        payslips = self.env['hr.payslip']

        # Determine which employees to process:
        # 1. From selected_employee_ids_json (set by selection checkbox widget)
        # 2. Or fallback to all eligible employee_ids if no specific employees are selected
        #    so clicking Select generates payslips and proceeds to the Pay Run page without error.
        employees = self._get_selected_employees()
        if not employees:
            employees = self.employee_ids

        if not employees:
            raise UserError(_("Please select at least one employee to generate payslips."))

        existing_emp_ids = set(run.slip_ids.mapped('employee_id.id'))
        for employee in employees:
            # Skip employees already in this run
            if employee.id in existing_emp_ids:
                continue

            # Skip employees not belonging to this run's company
            if employee.company_id and run.company_id and employee.company_id != run.company_id:
                continue

            # Generate a new payslip for employee in this pay run
            contract = False
            period_version = employee._hds_payroll_version(run.date_start, run.date_end)
            if period_version:
                c = period_version
                c_start = getattr(c, 'contract_date_start', False) or getattr(c, 'date_start', False)
                c_end = getattr(c, 'contract_date_end', False) or getattr(c, 'date_end', False)
                if (not c_start or c_start <= run.date_end) and (not c_end or c_end >= run.date_start):
                    contract = c

            if not contract:
                domain = [('employee_id', '=', employee.id)]
                if 'company_id' in self.env['hr.version']._fields and run.company_id:
                    domain += ['|', ('company_id', '=', False), ('company_id', '=', run.company_id.id)]
                if 'contract_date_start' in self.env['hr.version']._fields:
                    domain += [
                        '|', ('contract_date_start', '=', False), ('contract_date_start', '<=', run.date_end),
                        '|', ('contract_date_end', '=', False), ('contract_date_end', '>=', run.date_start),
                    ]
                contract = self.env['hr.version'].search(domain, limit=1, order='id desc')

            if not contract and period_version:
                contract = period_version

            if not contract:
                continue

            struct = getattr(contract, 'struct_id', False)
            if not struct and hasattr(contract, 'structure_type_id') and contract.structure_type_id:
                struct = self.env['hr.payroll.structure'].search([
                    ('type_id', '=', contract.structure_type_id.id)
                ], limit=1)

            if not struct:
                continue

            slip_vals = {
                'name': _('Salary Slip - %(emp)s - %(period)s') % {
                    'emp': employee.name,
                    'period': run.date_start.strftime('%B %Y')
                },
                'employee_id': employee.id,
                'contract_id': contract.id,
                'struct_id': run.struct_id.id if run.struct_id else struct.id,
                'date_from': run.date_start,
                'date_to': run.date_end,
                'payslip_run_id': run.id,
                'company_id': run.company_id.id,
            }
            slip = self.env['hr.payslip'].create(slip_vals)
            slip._populate_worked_days()
            slip._populate_inputs()
            payslips |= slip

        if payslips:
            draft_uncomputed = payslips.filtered(lambda s: s.state == 'draft' and not s.line_ids)
            if draft_uncomputed:
                run.action_compute_all()

        run._compute_counts()
        run._compute_financial_totals()
        run._compute_milestones()
        run._compute_duplicate_payslips()

        dup_slips = run.slip_ids.filtered(lambda s: s.has_duplicate_payslip and s.state != 'cancel')
        if dup_slips:
            emp_names = ", ".join(list(dict.fromkeys(dup_slips.mapped('employee_id.name'))))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Warning: Duplicate Payslips Detected"),
                    'message': _(
                        "This pay run includes %(count)s employee(s) for whom a payslip was already generated for this month: %(emps)s.\n\n"
                        "They have been flagged as 'Duplicate'."
                    ) % {
                        'count': len(dup_slips),
                        'emps': emp_names,
                    },
                    'type': 'warning',
                    'sticky': False,
                    'autocloseDelay': 5000,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'hr.payslip.run',
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                        'res_id': run.id,
                        'target': 'current',
                    },
                }
            }

        # Open the pay run form view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': run.id,
            'target': 'current',
        }

    def action_back(self):
        """Go back to the Pay Runs list view, discarding the newly created (empty) pay run."""
        payslip_run_id = self.env.context.get('active_id') or (self.payslip_run_id.id if self.payslip_run_id else False)
        if payslip_run_id:
            run = self.env['hr.payslip.run'].browse(payslip_run_id)
            # Only delete if it has no payslips (was just created, user went Back)
            if run.exists() and not run.slip_ids:
                run.unlink()
        return {'type': 'ir.actions.act_window_close'}

    def action_create_employee(self):
        """Open quick create form for employee."""
        return {
            'name': _('New Employee'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id if self.company_id else self.env.company.id,
            },
        }

    def action_launch_plan(self):
        """Open the standard Odoo 'Launch Plan' wizard (mail.activity.schedule) for the ticked employees."""
        self.ensure_one()
        employees = self._get_selected_employees()
        if not employees:
            raise UserError(_("Please tick at least one employee to launch a plan."))

        action = self.env['ir.actions.actions']._for_xml_id('hr.plan_wizard_action')
        action['context'] = {
            'plan_mode': True,
            'active_model': 'hr.employee',
            'active_id': employees[0].id,
            'active_ids': employees.ids,
            # Keeps the user on the pay run after scheduling (see mail.activity.schedule override)
            'hudson_payrun_launch_plan': True,
        }
        return action

    def action_reopen_selection(self):
        """Reopen this Select Employees dialog (ticks are kept on the record)."""
        self.ensure_one()
        run = self.payslip_run_id
        if not run:
            active_id = self.env.context.get('active_id')
            if active_id and self.env.context.get('active_model') == 'hr.payslip.run':
                run = self.env['hr.payslip.run'].browse(active_id)
        context = {}
        if run:
            context = {
                'active_id': run.id,
                'active_ids': [run.id],
                'active_model': 'hr.payslip.run',
                'default_payslip_run_id': run.id,
            }
        return {
            'name': _('Select Employees'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.employees',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': context,
        }

    def action_payslip_adjustment(self):
        """Open 'Generate Multiple Payslip Adjustments' for the ticked employees."""
        self.ensure_one()
        employees = self._get_selected_employees()
        if not employees:
            raise UserError(_("Please tick at least one employee to create a payslip adjustment."))

        run = self.payslip_run_id
        if not run:
            active_id = self.env.context.get('active_id')
            if active_id and self.env.context.get('active_model') == 'hr.payslip.run':
                run = self.env['hr.payslip.run'].browse(active_id)

        return {
            'name': _('Generate Multiple Payslip Adjustments'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.salary.adjustment.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_employee_ids': [(6, 0, employees.ids)],
                'default_company_id': (run.company_id or self.company_id or self.env.company).id,
                'default_payslip_run_id': run.id if run else False,
                'default_date_start': run.date_start if run else fields.Date.context_today(self),
                'default_employee_wizard_id': self.id,
            },
        }

    def compute_sheet(self):
        """Legacy method - delegates to action_select for backward compatibility."""
        return self.action_select()
