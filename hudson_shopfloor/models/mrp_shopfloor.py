# -*- coding: utf-8 -*-
from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError


def _dt(value):
    return fields.Datetime.to_string(value) if value else False


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    def action_open_shopfloor(self):
        """Desktop button of the Work Centers Overview: Shop Floor on this work center's tab."""
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('hudson_shopfloor.action_hudson_shopfloor')
        action['context'] = {'default_workcenter_id': self.id}
        return action


class MrpWorkcenterProductivity(models.Model):
    _inherit = 'mrp.workcenter.productivity'

    # Which operator the time line belongs to (several operators can share one user/device)
    employee_id = fields.Many2one('hr.employee', string='Employee', index='btree_not_null')


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def _prepare_timeline_vals(self, duration, date_start, date_end=False, employee_id=None):
        vals = super()._prepare_timeline_vals(duration, date_start, date_end, employee_id)
        employee_id = employee_id or self.env.context.get('sf_employee_id')
        if employee_id:
            employee = self.env['hr.employee'].browse(employee_id)
            vals['employee_id'] = employee.id
            vals['description'] = _('Time Tracking: %(user)s', user=employee.name)
        return vals

    def _sf_open_times(self, employee_id=False):
        """ Running time lines of the given operator (or of the current user when none). """
        times = self.time_ids.filtered(lambda t: not t.date_end)
        if employee_id:
            return times.filtered(lambda t: t.employee_id.id == employee_id)
        return times.filtered(lambda t: t.user_id == self.env.user and not t.employee_id)

    def _sf_timer_owner_domain(self, employee_id=False):
        if employee_id:
            return [('employee_id', '=', employee_id)]
        return [('user_id', '=', self.env.user.id), ('employee_id', '=', False)]

    # ------------------------------------------------------------------
    # Shop Floor actions
    # ------------------------------------------------------------------

    def shopfloor_start(self, employee_id=False):
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_('You cannot start a work order that is already done or cancelled.'))
        if self.state == 'blocked':
            raise UserError(_('This work order is waiting for a previous operation.'))
        if self._sf_open_times(employee_id):
            return True
        # An operator works on one work order at a time: pause the others
        self.env['mrp.workcenter.productivity'].search([
            ('date_end', '=', False), ('workorder_id', '!=', self.id),
            *self._sf_timer_owner_domain(employee_id),
        ])._close()
        workorder = self.with_context(sf_employee_id=employee_id)
        if self.time_ids.filtered(lambda t: not t.date_end and t.user_id == self.env.user):
            # button_start() skips a work order the user already times; another
            # operator on the same device still needs their own time line.
            self.env['mrp.workcenter.productivity'].create(
                workorder._prepare_timeline_vals(self.duration, fields.Datetime.now())
            )
        else:
            workorder.button_start()
        return True

    def shopfloor_pause(self, employee_id=False):
        self.ensure_one()
        self._sf_open_times(employee_id)._close()
        return True

    def shopfloor_mark_done(self):
        self.ensure_one()
        res = self.action_mark_as_done()
        return res if isinstance(res, dict) else True

    def shopfloor_close_production(self):
        """ Last operation: finish it and close the manufacturing order. """
        self.ensure_one()
        res = self.shopfloor_mark_done()
        if res is not True:
            return res
        return self.production_id.shopfloor_close_production()

    # ------------------------------------------------------------------
    # Data for the Shop Floor client action
    # ------------------------------------------------------------------

    def _sf_data(self, employee_id=False):
        self.ensure_one()
        production = self.production_id
        open_times = self.time_ids.filtered(lambda t: not t.date_end)
        closed_minutes = sum(self.time_ids.filtered('date_end').mapped('duration'))
        others = production.workorder_ids - self
        operators = [t.employee_id.name or t.user_id.name for t in open_times]
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'workcenter_id': [self.workcenter_id.id, self.workcenter_id.display_name],
            'production_id': [production.id, production.name],
            'production_state': production.state,
            'product': production.product_id.display_name,
            'product_tracking': production.product_tracking,
            'qty_production': production.product_qty,
            'qty_producing': production.qty_producing,
            'qty_remaining': self.qty_remaining,
            'uom': production.uom_id.name,
            'lots': ', '.join(production.lot_producing_ids.mapped('name')),
            'duration_expected': self.duration_expected,
            'duration_closed': closed_minutes,
            'timer_start': _dt(min(open_times.mapped('date_start'))) if open_times else False,
            'is_running': bool(open_times),
            'me_running': bool(self._sf_open_times(employee_id)),
            'operators': list(dict.fromkeys(operators)),
            'is_last': all(wo.state in ('done', 'cancel') for wo in others),
            'components': [move._sf_data() for move in self.move_raw_ids if move.state != 'cancel'],
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _sf_data(self):
        self.ensure_one()
        return {
            'id': self.id,
            'product': self.product_id.display_name,
            'product_uom_qty': self.product_uom_qty,
            'quantity': self.quantity,
            'picked': self.picked,
            'uom': self.uom_id.name,
            'tracking': self.has_tracking,
        }


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _sf_data(self, employee_id=False):
        self.ensure_one()
        workorders = self.workorder_ids.filtered(lambda wo: wo.state != 'cancel').sorted(lambda wo: (wo.sequence, wo.id))
        state_labels = dict(self._fields['state']._description_selection(self.env))
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'state_label': state_labels.get(self.state, self.state),
            'product': self.product_id.display_name,
            'product_tracking': self.product_tracking,
            'qty_production': self.product_qty,
            'qty_producing': self.qty_producing,
            'uom': self.uom_id.name,
            'lots': ', '.join(self.lot_producing_ids.mapped('name')),
            'components_availability_state': self.components_availability_state,
            'workorders': [wo._sf_data(employee_id) for wo in workorders],
            'all_wo_done': all(wo.state == 'done' for wo in workorders),
            'components': [move._sf_data() for move in self.move_raw_ids if move.state != 'cancel'],
        }

    @api.model
    def get_shopfloor_data(self, params=None):
        """ Everything the Shop Floor screen shows, in one call.

        params: tab ('overview' | 'my_wo' | workcenter id), employee_id,
        mo_ready, mo_pending, this_station, station_workcenter_ids,
        wo_states, search
        """
        params = params or {}
        employee_id = params.get('employee_id') or False
        Workcenter = self.env['mrp.workcenter']
        Workorder = self.env['mrp.workorder']

        station_ids = params.get('station_workcenter_ids') or []
        workcenters = Workcenter.browse(station_ids).exists() if station_ids else Workcenter.search([])
        workcenters = workcenters.sorted(lambda wc: (wc.sequence, wc.id))

        domain = [('state', 'in', ('confirmed', 'progress', 'to_close'))]
        mo_ready, mo_pending = params.get('mo_ready'), params.get('mo_pending')
        if mo_ready and not mo_pending:
            domain.append(('components_availability_state', '=', 'available'))
        elif mo_pending and not mo_ready:
            domain.append(('components_availability_state', 'in', ('expected', 'late', 'unavailable')))
        if params.get('this_station'):
            domain.append(('workorder_ids.workcenter_id', 'in', workcenters.ids))
        search = (params.get('search') or '').strip()
        if search:
            domain += ['|', '|', ('name', 'ilike', search), ('product_id', 'ilike', search),
                       ('workorder_ids.name', 'ilike', search)]
        productions = self.search(domain, order='priority desc, date_start asc, id asc')

        wo_states = params.get('wo_states') or ['blocked', 'ready', 'progress']
        wo_domain = [('production_id', 'in', productions.ids), ('state', 'in', wo_states)]
        counts = dict(Workorder._read_group(wo_domain, ['workcenter_id'], ['__count']))

        open_times = self.env['mrp.workcenter.productivity'].search([
            ('date_end', '=', False), ('workorder_id', '!=', False),
            *Workorder._sf_timer_owner_domain(employee_id),
        ])
        my_workorders = open_times.workorder_id.filtered(lambda wo: wo.state not in ('done', 'cancel'))

        tab = params.get('tab') or 'overview'
        result = {
            'workcenters': [{
                'id': wc.id,
                'name': wc.name,
                # No colour set: give each tab its own one (red, orange, yellow...)
                'color': wc.color or (index % 11) + 1,
                'working_state': wc.working_state,
                'count': counts.get(wc, 0),
            } for index, wc in enumerate(workcenters)],
            'overview_count': len(productions),
            'my_wo_count': len(my_workorders),
            'productions': [],
            'workorders': [],
        }
        if tab == 'overview':
            result['productions'] = [mo._sf_data(employee_id) for mo in productions]
        else:
            if tab == 'my_wo':
                workorders = my_workorders
            else:
                workorders = Workorder.search(wo_domain + [('workcenter_id', '=', int(tab))])
            workorders = workorders.sorted(lambda wo: (
                wo.state != 'progress', _dt(wo.production_id.date_start) or '', wo.sequence, wo.id,
            ))
            result['workorders'] = [wo._sf_data(employee_id) for wo in workorders]
        return result

    # ------------------------------------------------------------------
    # Shop Floor actions
    # ------------------------------------------------------------------

    def shopfloor_register_production(self, qty, lot_name=False):
        """ Set the quantity being produced (and its lot / serial number). """
        self.ensure_one()
        qty = float(qty or 0)
        if qty <= 0:
            raise UserError(_('The quantity to produce must be positive.'))
        if self.product_tracking == 'serial' and qty > 1:
            # One serial number per unit: Odoo's serial assignment wizard handles it
            self.qty_producing = qty
            self.set_qty_producing()
            return self.action_generate_serial()
        if lot_name and self.product_tracking in ('lot', 'serial'):
            lot = self.env['stock.lot'].search([
                ('name', '=', lot_name),
                ('product_id', '=', self.product_id.id),
                ('company_id', 'in', (self.company_id.id, False)),
            ], limit=1) or self.env['stock.lot'].create({
                'name': lot_name,
                'product_id': self.product_id.id,
                'company_id': self.company_id.id,
            })
            self.lot_producing_ids = [Command.set(lot.ids)]
        self.qty_producing = qty
        self.set_qty_producing()
        return True

    def shopfloor_register_component(self, move_id, qty=None):
        """ Register the consumed quantity of a component (full quantity by default). """
        self.ensure_one()
        move = self.move_raw_ids.filtered(lambda m: m.id == move_id)
        if not move:
            raise UserError(_('This component does not belong to %s.', self.name))
        if move.has_tracking in ('lot', 'serial'):
            return move.action_show_details()
        move.quantity = move.product_uom_qty if qty is None else float(qty)
        move.picked = True
        return True

    def shopfloor_add_components(self, lines, workorder_id=False):
        """ lines: [{'product_id': int, 'qty': float}] """
        self.ensure_one()
        workorder = self.env['mrp.workorder'].browse(workorder_id) if workorder_id else self.env['mrp.workorder']
        moves = self.env['stock.move']
        for line in lines:
            product = self.env['product.product'].browse(line['product_id'])
            vals = self._get_move_raw_values(product, float(line['qty']), product.uom_id, workorder.operation_id.id)
            if workorder:
                vals['workorder_id'] = workorder.id
            moves |= self.env['stock.move'].create(vals)
        moves._action_confirm()
        moves._action_assign()
        return True

    def shopfloor_close_production(self):
        """ Produce the whole remaining quantity (if nothing registered) and close the MO.

        Returns Odoo's wizard action when one is needed (backorder, consumption warning...).
        """
        self.ensure_one()
        if self.uom_id.is_zero(self.qty_producing):
            self.qty_producing = self.product_qty - self.qty_produced
            self.set_qty_producing()
        res = self.button_mark_done()
        return res if isinstance(res, dict) else True


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def get_shopfloor_employees(self, employee_ids=None):
        domain = [('id', 'in', employee_ids)] if employee_ids else [('user_id', '!=', False)]
        employees = self.search(domain)
        open_times = self.env['mrp.workcenter.productivity'].search([
            ('date_end', '=', False), ('employee_id', 'in', employees.ids), ('workorder_id', '!=', False),
        ])
        working = {t.employee_id.id: t for t in open_times}
        result = []
        for employee in employees.sudo():
            time = working.get(employee.id)
            result.append({
                'id': employee.id,
                'name': employee.name,
                'has_pin': bool(employee.pin),
                'working_wo': time and time.workorder_id.display_name or False,
                'working_since': time and _dt(time.date_start) or False,
            })
        return result
