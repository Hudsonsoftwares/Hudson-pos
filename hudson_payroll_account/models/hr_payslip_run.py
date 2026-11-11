# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    journal_id = fields.Many2one(
        'account.journal',
        string='Salary Journal',
        required=True,
        domain="[('type', '=', 'general')]",
        default=lambda self: self.env['account.journal'].search(
            [('type', '=', 'general')], limit=1
        ),
        help="Journal associated with this pay run batch."
    )
    move_count = fields.Integer(
        string='Accounting Entries Count',
        compute='_compute_move_count'
    )
    hds_move_status = fields.Char(string='Journal Entry Status', compute='_compute_move_count')

    @api.depends('slip_ids.move_id', 'slip_ids.move_id.state')
    def _compute_move_count(self):
        states = dict(self.env['account.move']._fields['state']._description_selection(self.env))
        for run in self:
            moves = run.slip_ids.mapped('move_id')
            run.move_count = len(moves)
            if len(moves) == 1:
                run.hds_move_status = states.get(moves.state, moves.state)
            else:
                run.hds_move_status = _('%s entries', len(moves)) if moves else False

    def write(self, vals):
        res = super(HrPayslipRun, self).write(vals)
        # When pay run is validated / paid, ensure its payslips' entries exist in draft state
        if vals.get('state') in ('confirmed', 'paid', 'close'):
            self.slip_ids.filtered(lambda slip: not slip.move_id and slip.state in ('done', 'paid'))._create_account_move()
        return res

    def action_open_account_moves(self):
        """Open the pay run's journal entry (or the list when its payslips have one entry each)."""
        self.ensure_one()
        self.slip_ids.filtered(lambda slip: not slip.move_id and slip.state in ('done', 'paid'))._create_account_move()
        moves = self.slip_ids.mapped('move_id')
        if len(moves) == 1:
            return {
                'name': _('Journal Entry'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_id': moves.id,
                'target': 'current',
            }
        # Journal Entries list (Date, Number, Partner, Reference, Journal, Total, Status), not the invoices one
        return {
            'name': _('Journal Entries - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(self.env.ref('hudson_payroll_account.view_move_tree_payroll').id, 'list'),
                      (self.env.ref('account.view_move_form').id, 'form')],
            'search_view_id': [self.env.ref('account.view_account_move_filter').id],
            'domain': [('id', 'in', moves.ids)],
            'context': {'create': False},
        }

    def action_open_draft_journal_entry(self):
        """Pay run 'More' menu > Journal Entry."""
        return self.action_open_account_moves()
