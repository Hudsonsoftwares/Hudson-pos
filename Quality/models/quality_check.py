# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _


class QualityCheck(models.Model):
    _name = 'quality.check'
    _description = 'Quality Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', default=lambda self: _('New'), copy=False, readonly=True)
    title = fields.Char(string='Title')
    
    @api.depends('name', 'title')
    def _compute_display_name(self):
        for check in self:
            if check.name != _('New') and check.title:
                check.display_name = f"{check.name} - {check.title}"
            elif check.name != _('New'):
                check.display_name = check.name
            elif check.title:
                check.display_name = check.title
            else:
                check.display_name = _('New')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('quality.check') or _('New')
        return super().create(vals_list)

    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)

    point_id = fields.Many2one('quality.point', string='Control Point', ondelete='set null')
    team_id = fields.Many2one('quality.team', string='Quality Team', tracking=True)
    user_id = fields.Many2one('res.users', string='Responsible',
                               default=lambda self: self.env.user)

    control_per = fields.Selection([
        ('operation', 'Operation'),
        ('product', 'Product'),
        ('quantity', 'Quantity'),
    ], default='operation', string='Control Per')

    test_type = fields.Selection(
        selection='_selection_test_type', default='passfail', string='Type', required=True)

    product_id = fields.Many2one('product.product', string='Product')
    lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number')
    qty_tested = fields.Float(string='Quantity Tested', default=1.0)
    qty_line = fields.Float(string='Quantity Line')
    qty_to_test = fields.Float(string='Quantity to Test')
    qty_failed = fields.Float(
        string='Quantity Failed', compute='_compute_qty_result', store=True,
        help='Tested quantity of a failed check (0 otherwise).')
    qty_passed = fields.Float(
        string='Quantity Passed', compute='_compute_qty_result', store=True,
        help='Tested quantity of a passed check (0 otherwise).')
    qty_checked = fields.Float(
        string='Quantity Checked', compute='_compute_qty_result', store=True,
        help='Tested quantity of a check that has a result (passed or failed); '
             '0 while the check is still to do. Always equals Quantity Passed + Quantity Failed.')
    testing_percentage_within_lot = fields.Float(
        string='Testing Percentage Within Lot', aggregator='avg',
        help='Percentage of the lot to test, copied from the control point.')
    # Source documents
    picking_id = fields.Many2one('stock.picking', string='Transfer', ondelete='cascade')
    repair_id = fields.Many2one('repair.order', string='Repair Order', ondelete='cascade')
    production_id = fields.Many2one('mrp.production', string='Production Order', ondelete='cascade')
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', ondelete='cascade')

    quality_state = fields.Selection([
        ('none', 'To Do'),
        ('pass', 'Passed'),
        ('fail', 'Failed'),
    ], default='none', string='Result', tracking=True, copy=False)

    date_create = fields.Datetime(default=fields.Datetime.now, string='Created On')
    date_done = fields.Datetime(string='Completed On', copy=False)

    # Text areas (copied from the point, editable per-check)
    instructions = fields.Html(string='Instructions')
    failure_message = fields.Html(string='Message If Failure')
    notes = fields.Html(string='Notes')
    additional_note = fields.Text(string='Additional Note')

    # ---- type-specific result fields --------------------------------------
    picture = fields.Binary(string='Picture')
    picture_filename = fields.Char()

    consumed_product_id = fields.Many2one('product.product', string='Product To Register')

    # aggregator='avg': in reports (graph/pivot) these show an average, a sum is meaningless
    measure = fields.Float(string='Measure', aggregator='avg')
    norm = fields.Float(string='Norm', aggregator='avg')
    norm_unit = fields.Char(string='Unit')
    tolerance_min = fields.Float(string='Min Tolerance', aggregator='avg')
    tolerance_max = fields.Float(string='Max Tolerance', aggregator='avg')

    # Devices
    device_id = fields.Many2one('quality.device', string='Device')
    obox_device_id = fields.Many2one('quality.obox.device', string='Obox Device')


    spreadsheet_template_id = fields.Many2one('quality.spreadsheet.template', string='Spreadsheet Template')
    spreadsheet_content = fields.Text(string='Spreadsheet')
    spreadsheet_success_cell = fields.Char(string='Success Cell')

    # Failure Locations (quantity control)
    failure_location_id = fields.Many2one(
        'stock.location', string='Failure Location',
        help='Where the failed quantity was moved to.')

    alert_ids = fields.One2many('quality.alert', 'check_id', string='Quality Alerts')
    alert_count = fields.Integer(compute='_compute_alert_count')

    @api.model
    def _selection_test_type(self):
        return self.env['quality.point'].TEST_TYPES

    @api.depends('alert_ids')
    def _compute_alert_count(self):
        for check in self:
            check.alert_count = self.env['quality.alert'].search_count([('check_id', '=', check.id)]) if check.id else 0

    @api.depends('quality_state', 'qty_tested')
    def _compute_qty_result(self):
        for check in self:
            check.qty_failed = check.qty_tested if check.quality_state == 'fail' else 0.0
            check.qty_passed = check.qty_tested if check.quality_state == 'pass' else 0.0
            check.qty_checked = check.qty_failed + check.qty_passed

    @api.onchange('point_id')
    def _onchange_point_id(self):
        for check in self:
            if check.point_id:
                p = check.point_id
                check.update({
                    'test_type': p.test_type,
                    'control_per': p.control_per,
                    'team_id': p.team_id.id,
                    'user_id': p.user_id.id or check.user_id.id,
                    'instructions': p.instructions,
                    'failure_message': p.failure_message,
                    'notes': p.notes,
                    'norm': p.norm,
                    'norm_unit': p.norm_unit,
                    'tolerance_min': p.tolerance_min,
                    'tolerance_max': p.tolerance_max,
                    'device_id': p.device_id.id,
                    'obox_device_id': p.obox_device_id.id,
                    'spreadsheet_template_id': p.spreadsheet_template_id.id,
                    'spreadsheet_content': p.spreadsheet_template_id.spreadsheet_data,
                    'spreadsheet_success_cell': p.spreadsheet_success_cell,
                    'testing_percentage_within_lot': p.testing_percentage_within_lot,
                })

    # -------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------
    def do_pass(self):
        self.write({'quality_state': 'pass', 'date_done': fields.Datetime.now()})
        return True

    def do_fail(self, failure_location_id=False):
        self.write({
            'quality_state': 'fail', 
            'date_done': fields.Datetime.now(),
            'failure_location_id': failure_location_id
        })
        self._redirect_stock_moves()
        # Quality alerts are no longer created automatically: the user raises
        # one with the "Quality Alert" button (see _get_create_alert_action).
        return True

    def _redirect_stock_moves(self):
        """If a failure_location_id is set, reroute the stock moves for the tested qty."""
        for check in self:
            if not check.failure_location_id or not check.picking_id:
                continue

            # Find matching stock.move records for this product
            moves = check.picking_id.move_ids.filtered(
                lambda m: m.product_id == check.product_id
            )
            if not moves:
                continue

            qty_to_redirect = check.qty_tested if check.control_per == 'quantity' else sum(moves.mapped('product_uom_qty'))
            
            redirected_qty = 0.0
            for move in moves:
                if redirected_qty >= qty_to_redirect:
                    break
                
                move_qty = move.product_uom_qty
                if move_qty <= 0.0:
                    continue
                    
                qty_remaining = qty_to_redirect - redirected_qty
                
                if move_qty <= qty_remaining:
                    # Redirect entire move
                    move.write({'location_dest_id': check.failure_location_id.id})
                    move.move_line_ids.write({'location_dest_id': check.failure_location_id.id})
                    redirected_qty += move_qty
                else:
                    # Partial redirect: we must split the move safely
                    new_move_vals = move._split(qty_remaining)
                    if new_move_vals:
                        for vals in new_move_vals:
                            vals['location_dest_id'] = check.failure_location_id.id
                        new_moves = self.env['stock.move'].create(new_move_vals)
                        new_moves._action_confirm()
                    redirected_qty += qty_remaining

    def do_measure(self):
        """Evaluate the Measure-type check against norm/tolerance and set the result."""
        self.ensure_one()
        for check in self:
            if check.test_type != 'measure':
                continue
            # tolerance_min and tolerance_max are absolute boundaries (e.g. 53.0 to 57.0)
            low = check.tolerance_min
            high = check.tolerance_max
            passed = low <= check.measure <= high
            if passed:
                check.write({
                    'quality_state': 'pass',
                    'date_done': fields.Datetime.now(),
                })
            else:
                return check._get_fail_wizard_action()
        return True

    def _get_fail_wizard_action(self, quality_check_wizard=False):
        """Action opening the 'Quality Check Failed' pop-up for this check.

        :param quality_check_wizard: optional quality.check.wizard record; when
            given, confirming the pop-up continues with its next pending check.
        """
        self.ensure_one()
        context = {'default_check_id': self.id}
        if quality_check_wizard:
            context['default_quality_check_wizard_id'] = quality_check_wizard.id
        return {
            'name': _('Quality Check Failed for %s') % (self.product_id.name or self.point_id.name or _('Measure')),
            'type': 'ir.actions.act_window',
            'res_model': 'quality.check.fail',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }

    def action_fail(self):
        """'Fail' button of the check form: let the user choose a failure
        location when the control point defines some, otherwise fail directly."""
        self.ensure_one()
        if self.point_id.failure_location_ids:
            return self._get_fail_wizard_action()
        return self.do_fail()

    def action_generate_alert(self):
        """'Create Alert' button of the check form: open a new, pre-filled alert."""
        self.ensure_one()
        return self._get_create_alert_action()

    def _get_create_alert_action(self):
        """Open a new (unsaved) quality alert form pre-filled from this check,
        so the user can enter the title and complete it before saving."""
        self.ensure_one()
        # only the check is passed in the context; quality.alert.default_get
        # fills the other values from it (so they don't leak as defaults into
        # other records created from the alert form, e.g. a quick-created product)
        context = {'default_check_id': self.id}
        return {
            'name': _('Quality Alert'),
            'type': 'ir.actions.act_window',
            'res_model': 'quality.alert',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': context,
        }

    @api.model
    def _get_alert_check(self, checks):
        """Failed check to raise an alert for, among ``checks``: the first
        failed one without an alert yet, otherwise the first failed one."""
        failed = checks.filtered(lambda c: c.quality_state == 'fail')
        return failed.filtered(lambda c: not c.alert_ids)[:1] or failed[:1]

    def action_view_alerts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'Quality.action_quality_alert')
        action['domain'] = [('check_id', '=', self.id)]
        action['context'] = {'default_check_id': self.id}
        return action

    # -------------------------------------------------------------------
    # Generation helpers, called from stock.picking / mrp.production
    # -------------------------------------------------------------------
    @api.model
    def _create_checks_from_points(self, points, common_vals, products=None):
        """Given a set of quality.point and a dict of common vals
        (picking_id/production_id/workorder_id...), create the quality
        checks according to each point's control_per setting."""
        checks = self.env['quality.check']
        
        domain = [('point_id', 'in', points.ids)]
        for k, v in common_vals.items():
            if k in ('picking_id', 'production_id', 'workorder_id', 'repair_id') and v:
                domain.append((k, '=', v))
        existing_checks = self.env['quality.check'].search(domain)
        existing_check_keys = {(c.point_id.id, c.product_id.id) for c in existing_checks}
        
        picking = self.env['stock.picking'].browse(common_vals['picking_id']) if common_vals.get('picking_id') else False
        production = self.env['mrp.production'].browse(common_vals['production_id']) if common_vals.get('production_id') else False
        workorder = self.env['mrp.workorder'].browse(common_vals['workorder_id']) if common_vals.get('workorder_id') else False
        repair = self.env['repair.order'].browse(common_vals['repair_id']) if common_vals.get('repair_id') else False

        vals_list = []
        for point in points:
            if not point._should_trigger():
                continue
            base_vals = dict(common_vals)
            base_vals.update({
                'point_id': point.id,
                'test_type': point.test_type,
                'control_per': point.control_per,
                'team_id': point.team_id.id,
                'user_id': point.user_id.id,
                'instructions': point.instructions,
                'failure_message': point.failure_message,
                'notes': point.notes,
                'norm': point.norm,
                'norm_unit': point.norm_unit,
                'tolerance_min': point.tolerance_min,
                'tolerance_max': point.tolerance_max,
                'device_id': point.device_id.id,
                'obox_device_id': point.obox_device_id.id,
                'spreadsheet_template_id': point.spreadsheet_template_id.id,
                'spreadsheet_content': point.spreadsheet_template_id.spreadsheet_data,
                'spreadsheet_success_cell': point.spreadsheet_success_cell,
                'testing_percentage_within_lot': point.testing_percentage_within_lot,
            })

            if point.control_per in ('product', 'quantity') and products:
                for product in products:
                    if (point.id, product.id) in existing_check_keys:
                        continue
                        
                    vals = dict(base_vals)
                    qty_line = 0.0
                    
                    if picking:
                        moves = picking.move_ids.filtered(lambda m: m.product_id.id == product.id)
                        qty_line = sum(moves.mapped('product_uom_qty'))
                    elif production:
                        qty_line = production.product_qty
                    elif workorder:
                        qty_line = workorder.qty_production
                    elif repair:
                        qty_line = repair.product_qty
                    
                    qty_to_test = qty_line
                    if point.control_per == 'quantity':
                        qty_to_test = qty_line * (point.testing_percentage_within_lot / 100.0)
                    
                    vals.update({
                        'title': '%s - %s' % (point.name, product.display_name),
                        'product_id': product.id,
                        'qty_line': qty_line,
                        'qty_to_test': qty_to_test,
                        'qty_tested': qty_to_test if qty_to_test > 0 else 1.0,
                    })
                    vals_list.append(vals)
            else:
                # 'operation' -> a single check
                if (point.id, False) in existing_check_keys:
                    continue
                    
                vals = dict(base_vals)
                qty_line = 0.0
                if picking:
                    qty_line = sum(picking.move_ids.mapped('product_uom_qty'))
                elif production:
                    qty_line = production.product_qty
                elif workorder:
                    qty_line = workorder.qty_production
                elif repair:
                    qty_line = repair.product_qty
                    
                vals.update({
                    'product_id': products[:1].id if products else False,
                    'qty_line': qty_line,
                    'qty_to_test': qty_line,
                    'qty_tested': qty_line if qty_line > 0 else 1.0,
                })
                vals_list.append(vals)

            point._mark_triggered()
            
        if vals_list:
            checks |= self.create(vals_list)
        return checks

    def action_open_spreadsheet(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'action_quality_spreadsheet',
            'params': {
                'spreadsheet_id': self.id,
                'res_model': 'quality.check'
            }
        }
