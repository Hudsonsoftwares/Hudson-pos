# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrEmployeeDeparture(models.Model):
    _inherit = 'hr.employee.departure'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for dep in records:
            dep._create_or_sync_final_settlement()
        return records

    def write(self, vals):
        res = super().write(vals)
        relevant_keys = {
            'departure_reason_id', 'departure_description',
            'notice_period_end_date', 'notice_period_start_date',
            'departure_date', 'dismissal_date', 'employee_id',
        }
        if any(k in vals for k in relevant_keys):
            for dep in self:
                dep._create_or_sync_final_settlement()
        return res

    def action_schedule(self):
        """
        Extends the 'Schedule' button in the 'End of collaboration' wizard.
        Schedules departure dates, aligns contract date_end, and automatically
        creates or syncs the pending Draft Final Settlement master record.
        """
        res = super().action_schedule()
        for dep in self:
            dep._create_or_sync_final_settlement()
        return res

    def action_register(self):
        """
        Extends the immediate departure registration action.
        Ensures immediate departures also create or sync the final settlement record.
        """
        res = super().action_register()
        for dep in self:
            dep._create_or_sync_final_settlement()
        return res

    def _create_or_sync_final_settlement(self):
        """
        Creates or updates the final.settlement record for the departing employee.
        Ensures idempotency and avoids duplicate active settlements.
        """
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return

        lwd = self.notice_period_end_date or self.departure_date or self.dismissal_date or fields.Date.today()

        # 1. Synchronize Active Contract date_end
        contract_model = 'hr.version' if 'hr.version' in self.env else ('hr.contract' if 'hr.contract' in self.env else False)
        if contract_model:
            contract = getattr(employee, 'version_id', False) or self.env[contract_model].search([
                ('employee_id', '=', employee.id)
            ], order='id desc', limit=1)
            if contract and (not contract.date_end or contract.date_end != lwd):
                contract.write({'date_end': lwd})

        # 2. Sync employee departure reason and description
        if self.departure_reason_id and employee.departure_reason_id != self.departure_reason_id:
            employee.departure_reason_id = self.departure_reason_id
        if self.departure_description and employee.departure_description != self.departure_description:
            employee.departure_description = self.departure_description

        # 3. Map Reason Name to Settlement Exit Reason using unified mapping
        exit_reason = self.env['final.settlement']._map_departure_reason_to_exit_reason(self.departure_reason_id)

        # 4. Check for existing active (non-cancelled) settlement
        existing = self.env['final.settlement'].search([
            ('employee_id', '=', employee.id),
            ('state', '!=', 'cancel'),
        ], limit=1)

        company = employee.company_id or self.env.company

        if existing:
            if existing.state == 'draft':
                existing.write({
                    'last_working_day': lwd,
                    'settlement_date': lwd,
                    'exit_reason': exit_reason,
                    'departure_reason_id': self.departure_reason_id.id if self.departure_reason_id else existing.departure_reason_id.id,
                    'departure_id': self.id,
                    'notes': self.departure_description or existing.notes,
                })
                try:
                    from ..services.final_settlement_calculation_service import FinalSettlementCalculationService
                    FinalSettlementCalculationService(self.env).compute_settlement(existing)
                except Exception as e:
                    _logger.warning("Could not recompute existing settlement on departure schedule: %s", str(e))
            return existing

        # 5. Find linked resignation if one exists
        resignation = self.env['hr.resignation'].search([
            ('employee_id', '=', employee.id),
            ('state', '!=', 'cancel'),
        ], order='id desc', limit=1) if 'hr.resignation' in self.env else False

        # 6. Create new Draft Final Settlement master record
        settlement_vals = {
            'employee_id': employee.id,
            'company_id': company.id,
            'last_working_day': lwd,
            'settlement_date': lwd,
            'exit_reason': exit_reason,
            'departure_reason_id': self.departure_reason_id.id if self.departure_reason_id else False,
            'departure_id': self.id,
            'resignation_id': resignation.id if resignation else False,
            'state': 'draft',
            'notes': self.departure_description or '',
        }
        settlement = self.env['final.settlement'].create(settlement_vals)

        # 7. Pre-compute statutory components (Gratuity, Leave Encashment, PT, Notice Pay)
        try:
            from ..services.final_settlement_calculation_service import FinalSettlementCalculationService
            FinalSettlementCalculationService(self.env).compute_settlement(settlement)
        except Exception as e:
            _logger.exception("Failed to pre-compute final settlement lines for employee %s: %s", employee.name, str(e))

        return settlement
