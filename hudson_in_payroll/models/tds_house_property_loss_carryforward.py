# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class TdsHousePropertyLossCarryforward(models.Model):
    """
    Section 71B House Property Loss Carry-Forward Ledger Model.
    Tracks unabsorbed House Property losses carried forward up to 8 Assessment Years (AY).
    """
    _name = 'tds.house.property.loss.carryforward'
    _description = 'House Property Loss Carry-Forward Ledger (Section 71B)'
    _order = 'financial_year_id desc, id desc'

    name = fields.Char(
        string="Loss Reference",
        compute='_compute_name',
        store=False
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        ondelete='cascade',
        help="Employee owning this unabsorbed House Property loss."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        related='employee_id.company_id',
        store=True,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='company_id.currency_id',
        readonly=True
    )
    financial_year_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        required=True,
        ondelete='restrict',
        help="Tax year in which the House Property loss originated."
    )
    financial_year_start_date = fields.Date(
        string="FY Start Date",
        related='financial_year_id.start_date',
        store=True,
        readonly=True
    )
    origin_assessment_year = fields.Char(
        string="Origin Assessment Year (AY)",
        help="Assessment year in which the loss originated (e.g. 2025-2026)."
    )
    expiry_assessment_year = fields.Char(
        string="Expiry Assessment Year (AY)",
        help="Final Assessment Year after which loss carry-forward expires (max 8 AYs u/s 71B)."
    )
    def _default_regime_code(self):
        ctx = self.env.context
        if ctx.get('default_regime_code') and ctx.get('default_regime_code') in ('new', 'old', 'both'):
            return ctx.get('default_regime_code')
        emp_id = ctx.get('default_employee_id')
        if not emp_id and ctx.get('active_model') == 'hr.employee':
            emp_id = ctx.get('active_id')
        elif not emp_id and ctx.get('active_model') == 'tds.employee.declaration':
            decl = self.env['tds.employee.declaration'].browse(ctx.get('active_id'))
            if decl.exists():
                return decl.regime_code or ('new' if decl.employee_id.hds_in_is_new_tax_regime else 'old')
        if emp_id:
            emp = self.env['hr.employee'].browse(emp_id)
            if emp.exists():
                return emp.hds_in_tax_regime or ('new' if emp.hds_in_is_new_tax_regime else 'old')
        company = self.env.company
        return company.hds_in_default_tax_regime or 'new'

    regime_code = fields.Selection(
        [('old', 'Old Regime'), ('new', 'New Regime'), ('both', 'Both Regimes')],
        string="Origin Regime",
        default=_default_regime_code,
        help="Tax regime under which the loss originated."
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'regime_code' in fields_list:
            ctx_regime = self.env.context.get('default_regime_code')
            if ctx_regime in ('new', 'old', 'both'):
                res['regime_code'] = ctx_regime
            else:
                emp_id = res.get('employee_id') or self.env.context.get('default_employee_id')
                if not emp_id and self.env.context.get('active_model') == 'hr.employee':
                    emp_id = self.env.context.get('active_id')
                elif not emp_id and self.env.context.get('active_model') == 'tds.employee.declaration':
                    decl = self.env['tds.employee.declaration'].browse(self.env.context.get('active_id'))
                    if decl.exists():
                        res['regime_code'] = decl.regime_code or ('new' if decl.employee_id.hds_in_is_new_tax_regime else 'old')
                        return res
                if emp_id:
                    emp = self.env['hr.employee'].browse(emp_id)
                    if emp.exists():
                        res['regime_code'] = emp.hds_in_tax_regime or ('new' if emp.hds_in_is_new_tax_regime else 'old')
        return res

    @api.onchange('employee_id')
    def _onchange_employee_id_set_regime(self):
        if self.employee_id:
            regime = self.employee_id.hds_in_tax_regime or ('new' if self.employee_id.hds_in_is_new_tax_regime else 'old')
            if regime in ('new', 'old'):
                self.regime_code = regime
    raw_loss_amount = fields.Monetary(
        string="Raw Loss Amount (₹)",
        currency_field='currency_id',
        default=0.0
    )
    unabsorbed_loss_amount = fields.Monetary(
        string="Original Unabsorbed Loss (₹)",
        currency_field='currency_id',
        required=True,
        default=0.0,
        help="Initial unabsorbed House Property loss amount carried forward."
    )
    current_year_set_off_amount = fields.Monetary(
        string="Current Year Set-Off (₹)",
        currency_field='currency_id',
        default=0.0
    )
    utilized_amount = fields.Monetary(
        string="Utilized / Set-Off Amount (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Loss amount set off against House Property income in subsequent financial years."
    )
    remaining_balance = fields.Monetary(
        string="Remaining Loss Available (₹)",
        currency_field='currency_id',
        compute='_compute_remaining_balance',
        store=True,
        help="Net unabsorbed loss remaining available for set-off."
    )
    is_expired = fields.Boolean(
        string="Expired",
        default=False
    )
    status = fields.Selection(
        [('draft', 'Draft'), ('active', 'Active'), ('fully_utilized', 'Fully Utilized'), ('expired', 'Expired')],
        string="Status",
        compute='_compute_status',
        store=True,
        default='draft'
    )
    # Statutory Verification Workflow (Matching LTA design)
    verification_status = fields.Selection([
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected')
    ], string="Verification Status", default='pending', required=True)
    verification_remarks = fields.Text(string="Verification Remarks")
    verified_by = fields.Many2one('res.users', string="Verified By", readonly=True)
    verified_on = fields.Datetime(string="Verified On", readonly=True)

    notes = fields.Text(
        string="Notes / Remarks"
    )

    def action_verify(self):
        for rec in self:
            rec.write({
                'verification_status': 'verified',
                'verified_by': self.env.user.id,
                'verified_on': fields.Datetime.now(),
            })

    def action_reject(self):
        for rec in self:
            rec.write({
                'verification_status': 'rejected',
                'verified_by': self.env.user.id,
                'verified_on': fields.Datetime.now(),
            })

    def action_reset_pending(self):
        for rec in self:
            rec.write({
                'verification_status': 'pending',
                'verified_by': False,
                'verified_on': False,
            })

    @api.depends('employee_id.name', 'financial_year_id.name', 'unabsorbed_loss_amount')
    def _compute_name(self):
        for rec in self:
            emp_str = rec.employee_id.name if rec.employee_id else 'Employee'
            fy_str = rec.financial_year_id.name if rec.financial_year_id else 'FY'
            rec.name = f"HP Loss 71B - {emp_str} [{fy_str}] (₹{rec.unabsorbed_loss_amount:,.2f})"

    @api.depends('unabsorbed_loss_amount', 'utilized_amount')
    def _compute_remaining_balance(self):
        for rec in self:
            rec.remaining_balance = max(0.0, float(rec.unabsorbed_loss_amount or 0.0) - float(rec.utilized_amount or 0.0))

    @api.depends('remaining_balance', 'unabsorbed_loss_amount', 'is_expired')
    def _compute_status(self):
        for rec in self:
            if rec.is_expired:
                rec.status = 'expired'
            elif not rec.unabsorbed_loss_amount or rec.unabsorbed_loss_amount <= 0.0:
                rec.status = 'draft'
            elif rec.remaining_balance <= 0.0 and rec.unabsorbed_loss_amount > 0.0:
                rec.status = 'fully_utilized'
            else:
                rec.status = 'active'
