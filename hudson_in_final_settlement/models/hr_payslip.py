# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_payslip_done(self):
        """
        Ensures exit leave encashment days on linked final settlement
        are deducted from Time Off allocations when settlement payslip is validated.
        """
        res = super(HrPayslip, self).action_payslip_done()
        for slip in self:
            settlement = self.env['final.settlement'].search([
                ('payslip_id', '=', slip.id),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if settlement and not settlement.is_exit_leave_deducted:
                settlement._deduct_exit_leave_allocations()
        return res

    def action_payslip_cancel(self):
        """
        Restores exit leave allocations if settlement payslip is cancelled
        and settlement is not yet paid.
        """
        res = super(HrPayslip, self).action_payslip_cancel()
        for slip in self:
            settlement = self.env['final.settlement'].search([
                ('payslip_id', '=', slip.id),
                ('state', 'in', ('draft', 'approved')),
            ], limit=1)
            if settlement and settlement.is_exit_leave_deducted:
                settlement._restore_exit_leave_allocations()
        return res
