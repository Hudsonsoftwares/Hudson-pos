# -*- coding: utf-8 -*-
import json
import logging
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class FinalSettlement(models.Model):
    _name = 'final.settlement'
    _description = 'Employee Final Settlement'
    _order = 'name desc, id desc'

    name = fields.Char(
        string="Settlement Number",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New')
    )
    
    @api.model
    def _default_company_id(self):
        emp_id = self.env.context.get('default_employee_id')
        if emp_id:
            emp = self.env['hr.employee'].browse(emp_id)
            if emp.exists() and emp.company_id:
                return emp.company_id
        return self.env.company

    # Employee Information
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        index=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Select the exiting employee for final settlement."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=_default_company_id,
        help="Company responsible for this final settlement."
    )
    department_id = fields.Many2one(
        'hr.department',
        string="Department",
        related='employee_id.department_id',
        store=True,
        readonly=True
    )
    job_id = fields.Many2one(
        'hr.job',
        string="Job Position",
        related='employee_id.job_id',
        store=True,
        readonly=True
    )

    # Exit Information
    resignation_id = fields.Many2one(
        'hr.resignation',
        string="Linked Resignation Request",
        domain="[('employee_id', '=', employee_id)]",
        help="Optional linked resignation record from the resignation workflow."
    )
    last_working_day = fields.Date(
        string="Last Working Day",
        required=True,
        default=fields.Date.today,
        help="Employee's final working day in the organization."
    )
    settlement_date = fields.Date(
        string="Settlement Date",
        required=True,
        default=fields.Date.today,
        help="Target processing date for final settlement calculation and payment."
    )
    exit_reason = fields.Selection([
        ('resignation', 'Resignation'),
        ('retirement', 'Retirement'),
        ('termination', 'Termination'),
        ('death', 'Death in Service'),
        ('contract_end', 'Contract Completion'),
        ('other', 'Other'),
    ], string="Exit Reason", default='resignation', required=True)
    departure_id = fields.Many2one(
        'hr.employee.departure',
        string="Departure Record",
        copy=False,
        help="Linked End of Collaboration departure record."
    )
    departure_reason_id = fields.Many2one(
        'hr.departure.reason',
        string="Departure Reason",
        help="Linked departure reason from End of Collaboration."
    )

    # Payroll Information
    payslip_id = fields.Many2one(
        'hr.payslip',
        string="Final Settlement Payslip",
        domain="[('employee_id', '=', employee_id)]",
        copy=False,
        help="Linked final settlement payslip sheet."
    )

    # Currency & Settlement Breakdown Lines
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='company_id.currency_id',
        store=True,
        readonly=True
    )
    line_ids = fields.One2many(
        'final.settlement.line',
        'settlement_id',
        string="Settlement Breakdown Lines",
        copy=True
    )

    # Settlement Financial Totals
    total_earnings = fields.Monetary(
        string="Total Earnings",
        currency_field='currency_id',
        compute='_compute_settlement_totals',
        store=True
    )
    total_deductions = fields.Monetary(
        string="Total Deductions",
        currency_field='currency_id',
        compute='_compute_settlement_totals',
        store=True
    )
    net_settlement_amount = fields.Monetary(
        string="Net Settlement Amount",
        currency_field='currency_id',
        compute='_compute_settlement_totals',
        store=True
    )

    @api.depends('line_ids', 'line_ids.amount', 'line_ids.line_type', 'line_ids.settlement_id')
    def _compute_settlement_totals(self):
        for record in self:
            earnings = sum(record.line_ids.filtered(lambda l: l.line_type == 'earning').mapped('amount'))
            deductions = sum(record.line_ids.filtered(lambda l: l.line_type == 'deduction').mapped('amount'))
            record.total_earnings = earnings
            record.total_deductions = deductions
            record.net_settlement_amount = earnings - deductions

    other_earnings_amount = fields.Monetary(
        string="Other Earnings",
        currency_field='currency_id',
        compute='_compute_other_earnings_amount',
        store=True,
        help="Earnings other than gratuity and leave encashment (e.g. final salary, notice pay)"
    )

    @api.depends('total_earnings', 'gratuity_gross_amount', 'leave_encash_gross_amount')
    def _compute_other_earnings_amount(self):
        for record in self:
            record.other_earnings_amount = (record.total_earnings - record.gratuity_gross_amount
                                            - record.leave_encash_gross_amount)

    # Gratuity & Tax Breakdown (Section 10(10) & Section 192)
    gratuity_gross_amount = fields.Monetary(
        string="Gross Gratuity Payable",
        currency_field='currency_id',
        help="Gross statutory gratuity calculated before exemption."
    )
    gratuity_exemption_amount = fields.Monetary(
        string="Eligible Exemption",
        currency_field='currency_id',
        default=2000000.0,
        help="Statutory tax exemption limit under Section 10(10)(iii) (default ₹20 Lakhs)."
    )
    gratuity_taxable_amount = fields.Monetary(
        string="Taxable Gratuity",
        currency_field='currency_id',
        compute='_compute_gratuity_taxable_amount',
        store=True,
        readonly=False,
        help="Gratuity amount exceeding the eligible exemption subject to income tax."
    )

    @api.depends('gratuity_gross_amount', 'gratuity_exemption_amount')
    def _compute_gratuity_taxable_amount(self):
        for record in self:
            gross = record.gratuity_gross_amount or 0.0
            exemption = record.gratuity_exemption_amount if record.gratuity_exemption_amount is not False else 2000000.0
            record.gratuity_taxable_amount = max(0.0, gross - exemption)

    # Leave Encashment & Tax Breakdown (Section 10(10AA) & Section 192)
    leave_encash_gross_amount = fields.Monetary(
        string="Gross Leave Encashment Payable",
        currency_field='currency_id',
        help="Gross statutory exit leave encashment calculated before exemption."
    )
    leave_encash_exemption_amount = fields.Monetary(
        string="Eligible Leave Exemption",
        currency_field='currency_id',
        compute='_compute_leave_encash_exemption_amount',
        store=True,
        readonly=False,
        help="Statutory tax exemption limit under Section 10(10AA) on exit/separation (default ₹25 Lakhs)."
    )
    leave_encash_taxable_amount = fields.Monetary(
        string="Taxable Leave Encashment",
        currency_field='currency_id',
        compute='_compute_leave_encash_taxable_amount',
        store=True,
        readonly=False,
        help="Leave encashment amount exceeding the eligible exemption subject to income tax."
    )

    @api.depends('exit_reason', 'departure_reason_id', 'settlement_date')
    def _compute_leave_encash_exemption_amount(self):
        for record in self:
            if not record.leave_encash_exemption_amount:
                ceiling = 2500000.0
                try:
                    p_val = self.env['hr.rule.parameter']._get_parameter_value(
                        'hds_in_leave_encashment_statutory_ceiling', record.settlement_date or fields.Date.today()
                    )
                    if not p_val:
                        p_val = self.env['hr.rule.parameter']._get_parameter_value(
                            'HDS_IN_TDS_LEAVE_ENCASHMENT_EXEMPTION_CEILING', record.settlement_date or fields.Date.today()
                        )
                    if p_val:
                        ceiling = float(p_val)
                except Exception:
                    ceiling = 2500000.0
                record.leave_encash_exemption_amount = ceiling

    @api.depends('leave_encash_gross_amount', 'leave_encash_exemption_amount', 'exit_reason', 'departure_reason_id')
    def _compute_leave_encash_taxable_amount(self):
        for record in self:
            gross = record.leave_encash_gross_amount or 0.0
            exemption = record.leave_encash_exemption_amount if (record.leave_encash_exemption_amount is not False and record.leave_encash_exemption_amount is not None) else 2500000.0
            record.leave_encash_taxable_amount = max(0.0, gross - exemption)

    # Workflow Status (Simplified 2-step lifecycle: Draft -> Approved)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('cancel', 'Cancelled'),
    ], string="Status", default='draft', required=True, copy=False, index=True)

    # Exit Leave Encashment Tracking & Time Off Allocation Sync
    exit_leave_encash_days = fields.Float(
        string="Exit Leave Encashment Days",
        readonly=True,
        copy=False,
        help="Number of eligible leave days calculated and encashed upon exit settlement."
    )
    exit_leave_deducted_data = fields.Text(
        string="Exit Leave Deducted Breakdown",
        readonly=True,
        copy=False,
        help="Structured JSON breakdown of Time Off allocations deducted upon settlement approval."
    )
    is_exit_leave_deducted = fields.Boolean(
        string="Exit Leave Deducted from Time Off",
        default=False,
        readonly=True,
        copy=False,
        help="Indicates whether encashed exit leave days have been deducted from Time Off allocations."
    )

    # Notes & Remarks
    notes = fields.Text(string="Notes & Remarks")

    def _deduct_exit_leave_allocations(self):
        """
        Deducts exit leave encashment days directly from active leave allocations using FIFO order.
        Creates ZERO hr.leave calendar records, eliminating work entry / attendance collisions.
        Matches the mechanism used by in-service leave encashment (hds.leave.encashment.request).
        """
        self.ensure_one()
        if self.is_exit_leave_deducted:
            return

        days_needed = float(self.exit_leave_encash_days or 0.0)
        if days_needed <= 0.0:
            exit_line = self.line_ids.filtered(lambda l: l.component_code == 'EXIT_LEAVE_ENCASH')
            if exit_line and exit_line[0].amount > 0.0:
                try:
                    # pyrefly: ignore [missing-import]
                    from odoo.addons.hudson_in_payroll.services.leave_encashment import LeaveEncashmentService
                    contract = getattr(self.employee_id, 'version_id', False) or self.env['hr.version'].search([
                        ('employee_id', '=', self.employee_id.id)
                    ], order='id desc', limit=1)
                    le_svc = LeaveEncashmentService(self.env)
                    calc_data = le_svc.data_service.prepare_calculation_data(
                        employee=self.employee_id,
                        contract=contract,
                        last_working_day=self.last_working_day,
                        calc_date=self.settlement_date
                    )
                    calc_res = le_svc.calculator.calculate(calc_data)
                    days_needed = float(calc_res.leave_days_used or 0.0)
                    self.exit_leave_encash_days = days_needed
                except Exception as e:
                    _logger.warning("Could not resolve exit leave encashment days on settlement %s: %s", self.name, str(e))

        if days_needed <= 0.0:
            return

        eligible_wets = self.env['hr.work.entry.type'].search([
            ('include_in_leave_encashment', '=', True)
        ])
        if not eligible_wets:
            _logger.info("No encashable leave types found for settlement %s", self.name)
            return

        alloc_model = self.env['hr.leave.allocation'].sudo()
        alloc_field = 'work_entry_type_id' if 'work_entry_type_id' in alloc_model._fields else 'holiday_status_id'

        ref_date = self.last_working_day or fields.Date.today()
        domain = [
            ('employee_id', '=', self.employee_id.id),
            (alloc_field, 'in', eligible_wets.ids),
            ('state', '=', 'validate'),
            '|',
            ('date_from', '=', False),
            ('date_from', '<=', ref_date),
            '|',
            ('date_to', '=', False),
            ('date_to', '>=', ref_date),
        ]

        allocations = alloc_model.search(domain)
        if not allocations:
            _logger.info("No active validated allocations found for employee %s on settlement %s", self.employee_id.name, self.name)
            return

        # FIFO ordering: expiring allocations first (chronological date_to), non-expiring last
        sorted_allocations = sorted(
            allocations,
            key=lambda a: (0, a.date_to) if a.date_to else (1, a.id)
        )

        deduction_records = []
        remaining_to_deduct = days_needed

        for alloc in sorted_allocations:
            if remaining_to_deduct <= 0.0:
                break

            if hasattr(alloc, 'virtual_remaining_leaves'):
                rem_raw = float(alloc.virtual_remaining_leaves)
                uom = getattr(alloc.work_entry_type_id, 'unit_of_measure', 'day') if hasattr(alloc, 'work_entry_type_id') else 'day'
                if uom == 'hour':
                    hours_per_day = (
                        self.employee_id.resource_calendar_id.hours_per_day
                        if self.employee_id and getattr(self.employee_id, 'resource_calendar_id', None) and self.employee_id.resource_calendar_id.hours_per_day
                        else 8.0
                    )
                    avail_in_alloc = rem_raw / (hours_per_day or 8.0)
                else:
                    avail_in_alloc = rem_raw
            else:
                taken = float(getattr(alloc, 'leaves_taken', 0.0) or 0.0)
                avail_in_alloc = float(alloc.number_of_days - taken)

            avail_in_alloc = min(avail_in_alloc, float(alloc.number_of_days))
            if avail_in_alloc <= 0.0:
                continue

            to_deduct = min(remaining_to_deduct, avail_in_alloc)
            original_number_of_days = float(alloc.number_of_days)
            new_number_of_days = max(0.0, float(original_number_of_days - to_deduct))

            alloc.write({'number_of_days': new_number_of_days})

            deduction_records.append({
                'allocation_id': alloc.id,
                'allocation_name': alloc.name or f"Allocation #{alloc.id}",
                'days': to_deduct,
                'original_number_of_days': original_number_of_days,
                'new_number_of_days': new_number_of_days,
            })
            remaining_to_deduct -= to_deduct

        total_deducted = sum(r['days'] for r in deduction_records)
        self.write({
            'is_exit_leave_deducted': True,
            'exit_leave_deducted_data': json.dumps(deduction_records),
        })

        if deduction_records:
            alloc_desc = ", ".join(f"{r['allocation_name']} ({r['days']} days)" for r in deduction_records)
            msg = _("Exit Leave Encashment: %s days deducted directly from Time Off allocation(s): %s.") % (total_deducted, alloc_desc)
            if hasattr(self, 'message_post'):
                try:
                    self.message_post(body=msg)
                except Exception:
                    pass
            _logger.info("Settlement %s: %s", self.name, msg)

    def _restore_exit_leave_allocations(self):
        """
        Restores deducted exit leave encashment days back to the employee's leave allocations.
        Called upon Reset to Draft, Cancel, or Unlink.
        """
        self.ensure_one()
        if not self.is_exit_leave_deducted:
            return

        alloc_model = self.env['hr.leave.allocation'].sudo()
        restored_days = 0.0

        if self.exit_leave_deducted_data:
            try:
                breakdown = json.loads(self.exit_leave_deducted_data)
                for entry in breakdown:
                    alloc_id = entry.get('allocation_id')
                    days = float(entry.get('days', 0.0))
                    if alloc_id and days > 0.0:
                        alloc = alloc_model.browse(alloc_id)
                        if alloc.exists():
                            alloc.write({'number_of_days': alloc.number_of_days + days})
                            restored_days += days
            except Exception as e:
                _logger.error("Failed to restore exit leave allocations for settlement %s: %s", self.name, str(e))

        self.write({
            'is_exit_leave_deducted': False,
            'exit_leave_deducted_data': False,
        })

        if restored_days > 0.0:
            msg = _("Exit Leave Encashment: %s days restored back to Time Off allocation(s).") % restored_days
            if hasattr(self, 'message_post'):
                try:
                    self.message_post(body=msg)
                except Exception:
                    pass
            _logger.info("Settlement %s: %s", self.name, msg)

    def action_compute_settlement(self):
        """Compute or recompute settlement breakdown lines via FinalSettlementCalculationService."""
        res_info = None
        for record in self:
            if record.state in ('approved', 'cancel'):
                raise ValidationError(_("Cannot recompute a settlement in %s state.") % record.state)

            if record.is_exit_leave_deducted:
                record._restore_exit_leave_allocations()

            # Auto-link existing departure month payslip if not already linked
            if not record.payslip_id and record.employee_id and record.last_working_day:
                lwd = record.last_working_day
                m_start = lwd.replace(day=1)
                existing_slip = self.env['hr.payslip'].search([
                    ('employee_id', '=', record.employee_id.id),
                    ('state', 'not in', ['cancel']),
                    ('date_from', '<=', lwd),
                    ('date_to', '>=', m_start),
                ], order='id desc', limit=1)
                if existing_slip:
                    record.payslip_id = existing_slip.id

            from ..services.final_settlement_calculation_service import FinalSettlementCalculationService
            service = FinalSettlementCalculationService(self.env)
            res_info = service.compute_settlement(record)
            if record.payslip_id and record.payslip_id.exists() and record.payslip_id.state == 'draft' and not record.payslip_id.line_ids:
                try:
                    record.payslip_id.compute_sheet()
                    # Resync settlement lines to reflect newly calculated payslip deductions (HDS_IN_TDS, etc.)
                    res_info = service.compute_settlement(record)
                except Exception:
                    pass

        if len(self) == 1 and res_info:
            msg = _(
                "Final settlement breakdown computed successfully. Processed %s component lines (Net Amount: %s)."
            ) % (res_info.get('processed_lines', 0), res_info.get('net_amount', 0.0))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Settlement Computed"),
                    'message': msg,
                    'sticky': False,
                    'type': 'success',
                    'next': {
                        'type': 'ir.actions.act_window_close',
                    },
                }
            }
        return True

    def action_submit(self):
        """Deprecated alias in 2-step lifecycle (Draft -> Approved). Directly approves settlement."""
        return self.action_approve()

    def action_approve(self):
        """Approve draft settlement, ensure breakdown is computed, deduct exit leave encashment days, and close active employment contract."""
        for record in self:
            if not record.line_ids:
                record.action_compute_settlement()
            record._deduct_exit_leave_allocations()
            record.write({'state': 'approved'})
            contract = getattr(record.employee_id, 'version_id', False) or self.env['hr.version'].search([
                ('employee_id', '=', record.employee_id.id)
            ], order='id desc', limit=1)
            if contract:
                vals = {'date_end': record.last_working_day}
                if 'state' in contract._fields:
                    vals['state'] = 'close'
                contract.write(vals)

    def action_reset_draft(self):
        """
        Resets approved settlement back to Draft state:
        1. Restores deducted exit leave encashment days back to employee's Time Off allocations.
        2. Cancels any unconfirmed linked settlement payslip (draft or verify) and unlinks it.
        3. Prevents reset if the linked payslip is already confirmed ('done') or paid ('paid').
        4. Re-opens closed employment contract if applicable.
        5. Resets settlement status to 'draft', re-enabling full editing and recalculation.
        """
        for record in self:
            # 1. Handle linked settlement payslip
            if record.payslip_id and record.payslip_id.exists():
                slip = record.payslip_id
                if slip.state in ('done', 'paid'):
                    raise ValidationError(_(
                        "Cannot reset settlement to Draft because the linked settlement payslip '%s' is already confirmed (%s). "
                        "Please cancel or refund the payslip first."
                    ) % (slip.name, slip.state))
                elif slip.state in ('draft', 'verify'):
                    try:
                        if hasattr(slip, 'action_payslip_cancel'):
                            slip.action_payslip_cancel()
                        else:
                            slip.write({'state': 'cancel'})
                    except Exception as e:
                        _logger.warning("Could not cancel draft payslip %s on settlement reset: %s", slip.name, str(e))
                        slip.write({'state': 'cancel'})
                    record.payslip_id = False

            # 2. Restore deducted Time Off leave days back to employee's allocations
            record._restore_exit_leave_allocations()

            # 3. Re-open employment contract if closed by this settlement
            contract = getattr(record.employee_id, 'version_id', False) or self.env['hr.version'].search([
                ('employee_id', '=', record.employee_id.id)
            ], order='id desc', limit=1)
            if contract and contract.date_end == record.last_working_day:
                vals = {'date_end': False}
                if 'state' in contract._fields and contract.state == 'close':
                    vals['state'] = 'open'
                contract.write(vals)

            # 4. Re-enable Draft status for editing and recalculation
            record.write({'state': 'draft'})

    def action_cancel(self):
        """Cancel settlement record, restore deducted exit leave days, and cancel any unconfirmed payslip."""
        for record in self:
            # Handle linked settlement payslip
            if record.payslip_id and record.payslip_id.exists():
                slip = record.payslip_id
                if slip.state in ('done', 'paid'):
                    raise ValidationError(_(
                        "Cannot cancel settlement because the linked settlement payslip '%s' is already confirmed (%s)."
                    ) % (slip.name, slip.state))
                elif slip.state in ('draft', 'verify'):
                    try:
                        if hasattr(slip, 'action_payslip_cancel'):
                            slip.action_payslip_cancel()
                        else:
                            slip.write({'state': 'cancel'})
                    except Exception as e:
                        _logger.warning("Could not cancel draft payslip %s on settlement cancel: %s", slip.name, str(e))
                        slip.write({'state': 'cancel'})

            record._restore_exit_leave_allocations()
            record.write({'state': 'cancel'})

    def action_mark_paid(self):
        """Deprecated. 'Paid' state is removed from settlement; payment is settled via payroll/payslip."""
        return True

    def action_generate_settlement_payslip(self):
        """
        Creates or opens a final settlement payslip using FINAL_SETTLEMENT_STRUCT.
        Sets date_from to first day of LWD's month, date_to to last_working_day.
        Computes sheet and synchronizes statutory deductions into settlement breakdown lines.
        """
        self.ensure_one()
        if self.payslip_id and self.payslip_id.exists():
            return {
                'name': _('Settlement Payslip'),
                'type': 'ir.actions.act_window',
                'res_model': 'hr.payslip',
                'res_id': self.payslip_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

        employee = self.employee_id
        lwd = self.last_working_day or fields.Date.today()
        from datetime import date
        date_from = date(lwd.year, lwd.month, 1)
        date_to = lwd

        struct = self.env.ref('hudson_in_payroll.hds_in_structure_final_settlement', raise_if_not_found=False)
        if not struct:
            struct = self.env['hr.payroll.structure'].search([('code', '=', 'FINAL_SETTLEMENT_STRUCT')], limit=1)
        if not struct:
            struct = self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)

        contract = getattr(employee, 'version_id', False) or self.env['hr.version'].search([
            ('employee_id', '=', employee.id)
        ], order='id desc', limit=1)

        # Enforce employee-company alignment before generating payslip
        if employee.company_id and self.company_id and employee.company_id != self.company_id:
            raise ValidationError(_(
                "Company Mismatch: Exiting employee '%s' belongs to company '%s', "
                "while this final settlement record is registered under company '%s'. "
                "Both must belong to the same legal company entity before generating a payslip."
            ) % (employee.name, employee.company_id.name, self.company_id.name))

        payslip_company = employee.company_id or self.company_id
        payslip_vals = {
            'employee_id': employee.id,
            'contract_id': contract.id if contract else False,
            'struct_id': struct.id if struct else False,
            'date_from': date_from,
            'date_to': date_to,
            'name': _("Final Settlement Payslip - %s - %s") % (employee.name, lwd.strftime('%b %Y')),
            'company_id': payslip_company.id,
        }
        payslip = self.env['hr.payslip'].create(payslip_vals)
        self.payslip_id = payslip.id
        try:
            payslip.compute_sheet()
        except Exception as e:
            _logger.warning("Error computing sheet for settlement payslip %s: %s", payslip.name, e)

        try:
            from ..services.final_settlement_calculation_service import FinalSettlementCalculationService
            service = FinalSettlementCalculationService(self.env)
            service.compute_settlement(self)
        except Exception as e:
            _logger.warning("Error syncing deductions into settlement %s: %s", self.name, e)

        return {
            'name': _('Settlement Payslip'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'res_id': payslip.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_payslip(self):
        """Action for smart button to view or create linked settlement payslip."""
        self.ensure_one()
        if not self.payslip_id:
            return self.action_generate_settlement_payslip()
        if self.payslip_id.line_ids:
            try:
                from ..services.final_settlement_calculation_service import FinalSettlementCalculationService
                service = FinalSettlementCalculationService(self.env)
                service.compute_settlement(self)
            except Exception:
                pass
        return {
            'name': _('Settlement Payslip'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'res_id': self.payslip_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print_settlement_report(self):
        """Action for header button to generate and print/download the Full & Final Settlement PDF report."""
        self.ensure_one()
        return self.env.ref('hudson_in_final_settlement.action_report_final_settlement').report_action(self)

    def _get_settlement_report_data(self):
        """Extract structured employee profile, banking, statutory, and exit metadata for the F&F report."""
        self.ensure_one()
        emp = self.employee_id
        contract = getattr(emp, 'version_id', False) or self.env['hr.version'].search([
            ('employee_id', '=', emp.id)
        ], order='id desc', limit=1)

        pan = getattr(emp, 'hds_in_pan', False) or getattr(emp, 'pan_no', False) or getattr(emp, 'pan', False) or getattr(emp, 'identification_id', False) or '-'
        uan = getattr(emp, 'hds_in_uan', False) or getattr(emp, 'hds_in_epf_uan', False) or getattr(emp, 'uan', False) or '-'
        epf = getattr(emp, 'hds_in_pf_member_id', False) or getattr(emp, 'hds_in_epf_number', False) or getattr(emp, 'pf_number', False) or '-'

        bank_acc = getattr(emp, 'bank_account_id', False)
        bank_no = bank_acc.acc_number if bank_acc else '-'
        bank_name = (bank_acc.bank_id.name if bank_acc and bank_acc.bank_id else getattr(bank_acc, 'bank_name', '-')) or '-'
        ifsc = (bank_acc.bank_id.bic if bank_acc and bank_acc.bank_id else getattr(bank_acc, 'ifsc_code', '-')) or '-'

        emp_code = (
            getattr(emp, 'registration_number', False)
            or getattr(emp, 'pin', False)
            or getattr(emp, 'barcode', False)
            or f"EMP-{emp.id:04d}"
        )

        doj = getattr(emp, 'joining_date', False) or (contract.date_start if contract else False) or '-'
        exit_reason_label = dict(self._fields['exit_reason'].selection).get(self.exit_reason, (self.exit_reason or '').title())

        amount_in_words = ""
        if self.currency_id and hasattr(self.currency_id, 'amount_to_text'):
            try:
                amount_in_words = self.currency_id.amount_to_text(abs(self.net_settlement_amount))
            except Exception:
                amount_in_words = ""

        return {
            'emp_code': emp_code,
            'pan': pan,
            'uan': uan,
            'epf': epf,
            'bank_name': bank_name,
            'bank_no': bank_no,
            'ifsc': ifsc,
            'doj': doj,
            'exit_reason_label': exit_reason_label,
            'amount_in_words': amount_in_words,
        }


    @api.constrains('resignation_id', 'state')
    def _check_unique_resignation_settlement(self):
        for record in self:
            if record.resignation_id and record.state != 'cancel':
                domain = [
                    ('resignation_id', '=', record.resignation_id.id),
                    ('state', '!=', 'cancel'),
                    ('id', '!=', record.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_(
                        "An active Final Settlement record already exists for Resignation Request '%s'. "
                        "Duplicate settlements are not allowed."
                    ) % record.resignation_id.name)

    @api.constrains('employee_id', 'company_id')
    def _check_employee_company_alignment(self):
        for record in self:
            if record.employee_id and record.company_id and record.employee_id.company_id:
                if record.employee_id.company_id != record.company_id:
                    raise ValidationError(_(
                        "Company Mismatch: Exiting employee '%s' belongs to company '%s', "
                        "but final settlement '%s' is registered under company '%s'. "
                        "The settlement and employee must belong to the same company."
                    ) % (
                        record.employee_id.name,
                        record.employee_id.company_id.name,
                        record.name or _('New'),
                        record.company_id.name
                    ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('final.settlement') or _('New')
            if vals.get('employee_id') and not vals.get('company_id'):
                emp = self.env['hr.employee'].browse(vals['employee_id'])
                if emp.company_id:
                    vals['company_id'] = emp.company_id.id
        return super(FinalSettlement, self).create(vals_list)

    def unlink(self):
        for record in self:
            if record.is_exit_leave_deducted:
                record._restore_exit_leave_allocations()
        return super(FinalSettlement, self).unlink()

    @api.model
    def _map_departure_reason_to_exit_reason(self, departure_reason):
        """
        Maps hr.departure.reason record (or reason string/id) to final.settlement exit_reason selection.
        """
        if not departure_reason:
            return 'resignation'
        if isinstance(departure_reason, (int, str)) and str(departure_reason).isdigit():
            departure_reason = self.env['hr.departure.reason'].browse(int(departure_reason))

        if hasattr(departure_reason, 'get_external_id'):
            xml_id = departure_reason.get_external_id().get(departure_reason.id, '')
            if xml_id:
                if 'departure_fired' in xml_id:
                    return 'termination'
                elif 'departure_retired' in xml_id:
                    return 'retirement'
                elif 'departure_dead' in xml_id:
                    return 'death'
                elif 'departure_contract_end' in xml_id:
                    return 'contract_end'
                elif 'departure_other' in xml_id:
                    return 'other'
                elif 'departure_resigned' in xml_id:
                    return 'resignation'

        name = getattr(departure_reason, 'name', str(departure_reason)) or ''
        name_lower = name.strip().lower()
        if any(k in name_lower for k in ['fire', 'dismiss', 'terminat', 'layoff', 'discharge']):
            return 'termination'
        elif any(k in name_lower for k in ['retir', 'superannuat']):
            return 'retirement'
        elif any(k in name_lower for k in ['dead', 'death', 'demise', 'fatal', 'decease']):
            return 'death'
        elif any(k in name_lower for k in ['contract', 'complet', 'expir']):
            return 'contract_end'
        elif any(k in name_lower for k in ['other', 'mutual', 'miscellan']):
            return 'other'
        elif any(k in name_lower for k in ['resign', 'reliev', 'quit', 'notice']):
            return 'resignation'
        return 'other'

    @api.model
    def _get_departure_reason_for_exit_reason(self, exit_reason):
        """
        Maps final.settlement exit_reason selection to the corresponding hr.departure.reason record.
        """
        if not exit_reason:
            return self.env['hr.departure.reason']

        xml_id_map = {
            'termination': 'hr.departure_fired',
            'resignation': 'hr.departure_resigned',
            'retirement': 'hr.departure_retired',
            'death': 'hr.departure_dead',
            'contract_end': 'hudson_in_final_settlement.departure_contract_end',
            'other': 'hudson_in_final_settlement.departure_other',
        }
        xml_id = xml_id_map.get(exit_reason)
        reason = self.env.ref(xml_id, raise_if_not_found=False) if xml_id else False
        if reason:
            return reason

        patterns_map = {
            'termination': ['fire', 'terminat', 'dismiss'],
            'resignation': ['resign', 'reliev'],
            'retirement': ['retir'],
            'death': ['dead', 'death'],
            'contract_end': ['contract', 'complet'],
            'other': ['other'],
        }
        for pat in patterns_map.get(exit_reason, []):
            matched = self.env['hr.departure.reason'].search([('name', 'ilike', pat)], limit=1)
            if matched:
                return matched

        return self.env['hr.departure.reason']

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.employee_id and self.company_id and self.employee_id.company_id and self.employee_id.company_id != self.company_id:
            self.employee_id = False

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            if self.employee_id.company_id:
                self.company_id = self.employee_id.company_id
            # 1. Check End of Collaboration departure record or reason
            departure = self.departure_id or getattr(self.employee_id, 'departure_id', False)
            if not departure and 'hr.employee.departure' in self.env:
                departure = self.env['hr.employee.departure'].search([
                    ('employee_id', '=', self.employee_id.id),
                ], order='id desc', limit=1)

            departure_reason = False
            if departure:
                self.departure_id = departure.id
                lwd = departure.notice_period_end_date or departure.departure_date or departure.dismissal_date
                if lwd:
                    self.last_working_day = lwd
                    self.settlement_date = lwd
                if departure.departure_reason_id:
                    departure_reason = departure.departure_reason_id
            elif getattr(self.employee_id, 'departure_reason_id', None):
                departure_reason = self.employee_id.departure_reason_id

            if getattr(self.employee_id, 'departure_date', None) and not self.last_working_day:
                self.last_working_day = self.employee_id.departure_date
                self.settlement_date = self.employee_id.departure_date

            # 2. Check resignation
            res = self.env['hr.resignation'].search([
                ('employee_id', '=', self.employee_id.id),
                ('state', '!=', 'cancel')
            ], order='id desc', limit=1) if 'hr.resignation' in self.env else False

            if res:
                self.resignation_id = res.id
                if getattr(res, 'approved_revealing_date', None):
                    self.last_working_day = res.approved_revealing_date
                    self.settlement_date = res.approved_revealing_date
                elif getattr(res, 'expected_revealing_date', None):
                    self.last_working_day = res.expected_revealing_date
                    self.settlement_date = res.expected_revealing_date
                if not departure_reason:
                    departure_reason = self._get_departure_reason_for_exit_reason('resignation')

            # 3. Synchronize Departure Reason & Exit Reason
            if departure_reason:
                self.departure_reason_id = departure_reason.id
                self.exit_reason = self._map_departure_reason_to_exit_reason(departure_reason)
            elif not self.exit_reason:
                self.exit_reason = 'resignation'

    @api.onchange('departure_reason_id')
    def _onchange_departure_reason_id(self):
        if self.departure_reason_id:
            self.exit_reason = self._map_departure_reason_to_exit_reason(self.departure_reason_id)
            if self.exit_reason == 'retirement':
                ceiling = 2500000.0
                try:
                    p_val = self.env['hr.rule.parameter']._get_parameter_value(
                        'hds_in_leave_encashment_statutory_ceiling', self.settlement_date or fields.Date.today()
                    ) or self.env['hr.rule.parameter']._get_parameter_value(
                        'HDS_IN_TDS_LEAVE_ENCASHMENT_EXEMPTION_CEILING', self.settlement_date or fields.Date.today()
                    )
                    if p_val:
                        ceiling = float(p_val)
                except Exception:
                    ceiling = 2500000.0
                self.leave_encash_exemption_amount = ceiling
            else:
                self.leave_encash_exemption_amount = 0.0

    @api.onchange('exit_reason')
    def _onchange_exit_reason(self):
        if self.exit_reason:
            matched_reason = self._get_departure_reason_for_exit_reason(self.exit_reason)
            if matched_reason and (not self.departure_reason_id or self._map_departure_reason_to_exit_reason(self.departure_reason_id) != self.exit_reason):
                self.departure_reason_id = matched_reason.id
            if self.exit_reason == 'retirement':
                ceiling = 2500000.0
                try:
                    p_val = self.env['hr.rule.parameter']._get_parameter_value(
                        'hds_in_leave_encashment_statutory_ceiling', self.settlement_date or fields.Date.today()
                    ) or self.env['hr.rule.parameter']._get_parameter_value(
                        'HDS_IN_TDS_LEAVE_ENCASHMENT_EXEMPTION_CEILING', self.settlement_date or fields.Date.today()
                    )
                    if p_val:
                        ceiling = float(p_val)
                except Exception:
                    ceiling = 2500000.0
                self.leave_encash_exemption_amount = ceiling
            else:
                self.leave_encash_exemption_amount = 0.0

    @api.onchange('resignation_id')
    def _onchange_resignation_id(self):
        if self.resignation_id:
            if self.resignation_id.employee_id:
                self.employee_id = self.resignation_id.employee_id.id
            if getattr(self.resignation_id, 'approved_revealing_date', None):
                self.last_working_day = self.resignation_id.approved_revealing_date
                self.settlement_date = self.resignation_id.approved_revealing_date
            elif getattr(self.resignation_id, 'expected_revealing_date', None):
                self.last_working_day = self.resignation_id.expected_revealing_date
                self.settlement_date = self.resignation_id.expected_revealing_date
            self.exit_reason = 'resignation'
            matched = self._get_departure_reason_for_exit_reason('resignation')
            if matched:
                self.departure_reason_id = matched.id
