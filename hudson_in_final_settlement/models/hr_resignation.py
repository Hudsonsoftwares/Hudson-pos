import logging
# pyrefly: ignore [missing-import]
from odoo import fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrResignation(models.Model):
    _inherit = 'hr.resignation'

    final_settlement_ids = fields.One2many(
        'final.settlement',
        'resignation_id',
        string="Final Settlements"
    )
    settlement_count = fields.Integer(
        string="Settlements Count",
        compute='_compute_settlement_count'
    )
    final_settlement_count = fields.Integer(
        string="Final Settlement Count",
        compute='_compute_settlement_count'
    )

    def _compute_settlement_count(self):
        for record in self:
            count = len(record.final_settlement_ids.filtered(lambda s: s.state != 'cancel'))
            record.settlement_count = count
            record.final_settlement_count = count

    def action_create_final_settlement(self):
        """
        Creates an India Statutory Final Settlement master record from an approved resignation.
        Prevents duplicate active settlement creation.
        """
        self.ensure_one()
        if self.state not in ('approved', 'confirm'):
            raise UserError(_("Final Settlement can only be created for approved or confirmed resignation requests."))

        # Check for existing active settlement
        existing = self.env['final.settlement'].search([
            ('resignation_id', '=', self.id),
            ('state', '!=', 'cancel')
        ], limit=1)

        if existing:
            return {
                'name': _('Final Settlement'),
                'type': 'ir.actions.act_window',
                'res_model': 'final.settlement',
                'res_id': existing.id,
                'view_mode': 'form',
                'target': 'current',
            }

        last_day = self.approved_revealing_date or self.expected_revealing_date or fields.Date.today()
        company = self.employee_id.company_id or self.env.company

        departure_reason = self.env['final.settlement']._get_departure_reason_for_exit_reason('resignation')
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee_id.id,
            'company_id': company.id,
            'resignation_id': self.id,
            'last_working_day': last_day,
            'settlement_date': fields.Date.today(),
            'exit_reason': 'resignation',
            'departure_reason_id': departure_reason.id if departure_reason else False,
            'state': 'draft',
        })

        # Pre-compute India statutory components (Gratuity, Leave Encashment, Notice Pay)
        try:
            from ..services.final_settlement_calculation_service import FinalSettlementCalculationService
            calc_service = FinalSettlementCalculationService(self.env)
            calc_service.compute_settlement(settlement)
        except Exception as e:
            _logger.exception("Failed to pre-compute final settlement lines for %s: %s", settlement.name, str(e))

        return {
            'name': _('Final Settlement'),
            'type': 'ir.actions.act_window',
            'res_model': 'final.settlement',
            'res_id': settlement.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_final_settlement(self):
        """Action for smart button to view or create linked final settlement."""
        self.ensure_one()
        settlements = self.final_settlement_ids.filtered(lambda s: s.state != 'cancel')
        if not settlements:
            return self.action_create_final_settlement()

        if len(settlements) == 1:
            return {
                'name': _('Final Settlement'),
                'type': 'ir.actions.act_window',
                'res_model': 'final.settlement',
                'res_id': settlements[0].id,
                'view_mode': 'form',
                'target': 'current',
            }

        return {
            'name': _('Final Settlements'),
            'type': 'ir.actions.act_window',
            'res_model': 'final.settlement',
            'domain': [('resignation_id', '=', self.id), ('state', '!=', 'cancel')],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_final_settlement(self):
        """Alias for action_open_final_settlement for backward compatibility."""
        return self.action_open_final_settlement()

    def action_approve(self):
        """
        Override approval to automatically generate draft India Final Settlement
        with Gratuity and Leave Encashment pre-calculated.
        """
        res = super().action_approve()
        for record in self:
            record._auto_create_final_settlement()
        return res

    def _auto_create_final_settlement(self):
        """
        Automatically creates a draft Final Settlement record with pre-fetched data
        and computes breakdown lines upon resignation approval.
        """
        for record in self:
            existing = self.env['final.settlement'].search([
                ('resignation_id', '=', record.id),
                ('state', '!=', 'cancel')
            ], limit=1)
            if not existing:
                last_day = record.approved_revealing_date or record.expected_revealing_date or fields.Date.today()
                company = record.employee_id.company_id or self.env.company
                departure_reason = self.env['final.settlement']._get_departure_reason_for_exit_reason('resignation')
                settlement = self.env['final.settlement'].create({
                    'employee_id': record.employee_id.id,
                    'company_id': company.id,
                    'resignation_id': record.id,
                    'last_working_day': last_day,
                    'settlement_date': fields.Date.today(),
                    'exit_reason': 'resignation',
                    'departure_reason_id': departure_reason.id if departure_reason else False,
                    'state': 'draft',
                })
                # Automatically compute settlement breakdown lines
                try:
                    from ..services.final_settlement_calculation_service import FinalSettlementCalculationService
                    calc_service = FinalSettlementCalculationService(self.env)
                    calc_service.compute_settlement(settlement)
                except Exception as e:
                    _logger.exception("Failed to auto-compute final settlement lines for %s (resignation %s): %s", settlement.name, record.name, str(e))
