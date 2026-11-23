# -*- coding: utf-8 -*-
"""Refresh waitlist estimates when the POS's own table state changes.

Notification only. Table availability stays entirely in the standard POS flow: a table is
taken while it has a draft order, and the POS payment / cancel flow releases it by moving
that order out of draft. Nothing here decides or changes whether a table is free; the
waitlist estimate (``pos.waitlist.entry._queue_wait_estimates``) reads that state on every
request. These hooks only tell the open POS Waitlist screens and backend Waitlist views to
reload when it changes (the guest status page polls by itself).
"""
from odoo import api, models

from .pos_waitlist_entry import EVENT_UPDATED

# Writing one of these on a table can change what the waitlist can seat (merge = parent_id).
_TABLE_CAPACITY_FIELDS = {'seats', 'active', 'floor_id', 'parent_id'}


def notify_waitlist_floors(env, floors):
    """Ask every POS / backend view with waiting guests on ``floors`` to reload (best effort)."""
    if not floors:
        return
    waiting = env['pos.waitlist.entry'].sudo().search([
        ('state', '=', 'waiting'), ('config_id.floor_ids', 'in', floors.ids),
    ])
    for config in waiting.config_id:
        try:
            config._notify(EVENT_UPDATED, {'entries': []})
        except Exception:  # noqa: BLE001 - never block a POS order on the bus
            pass
    # Backend Waitlist list / form show the same live estimate (estimated_wait_label).
    waiting._notify_backend()


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        # A waitlist guest's own order (uuid issued when they were seated): link it to them.
        uuids = [o.uuid for o in orders if o.uuid]
        if uuids:
            for entry in self.env['pos.waitlist.entry'].sudo().search([
                    ('pos_order_uuid', 'in', uuids), ('pos_order_id', '=', False)]):
                entry.pos_order_id = orders.filtered(lambda o: o.uuid == entry.pos_order_uuid)[:1]
        # A new order on a table: that table is now occupied.
        notify_waitlist_floors(self.env, orders.sudo().table_id.floor_id)
        return orders

    def _get_open_order(self, order):
        """One order per party, also when several parties share a table.

        pos_restaurant attaches an incoming draft table order to ANY draft order of the same
        table (two terminals opening one table end up on one order). With waitlist guests
        sharing a table, each party has its own order, so (same approach as the KDS self-order
        fix in hudson_kitchen_display):

        * the own order of a guest seated at a shared table (uuid issued at seating) only ever
          matches itself: created as its own order, then updated by its own uuid;
        * no other order is ever merged into it: an order already on the server updates itself,
          a new one goes to the table's other open order, else is created.

        Every other case (any table without a shared waitlist seating) is the standard one.
        """
        uuid = order.get('uuid')
        if not (uuid and order.get('table_id') and order.get('state') == 'draft'):
            return super()._get_open_order(order)
        Entry = self.env['pos.waitlist.entry'].sudo()
        if Entry.search_count([('shared_seating', '=', True), ('pos_order_uuid', '=', uuid)], limit=1):
            return self.search([('uuid', '=', uuid)], limit=1)
        found = super()._get_open_order(order)
        if not found or found.uuid == uuid or not Entry.search_count([
                ('shared_seating', '=', True), ('pos_order_uuid', '=', found.uuid)], limit=1):
            return found
        own = self.search([('uuid', '=', uuid)], limit=1)
        if own:
            return own
        drafts = self.search([('table_id', '=', found.table_id.id), ('state', '=', 'draft'),
                              ('config_id', '=', found.config_id.id)], order='id desc')
        separate = set(Entry.search([('shared_seating', '=', True),
                                     ('pos_order_uuid', 'in', drafts.mapped('uuid'))]).mapped('pos_order_uuid'))
        return drafts.filtered(lambda o: o.uuid not in separate)[:1]

    def write(self, vals):
        if 'state' not in vals and 'table_id' not in vals:
            return super().write(vals)
        # Paid / cancelled (the table is released) or moved to another table. The POS sync
        # re-sends state / table on every save: only real changes are worth a refresh.
        changed = self.sudo().filtered(lambda o: (
            ('state' in vals and vals['state'] != o.state)
            or ('table_id' in vals and (vals['table_id'] or False) != o.table_id.id)))
        floors = changed.table_id.floor_id
        res = super().write(vals)
        notify_waitlist_floors(self.env, floors | changed.table_id.floor_id)
        return res


class RestaurantTable(models.Model):
    _inherit = 'restaurant.table'

    def write(self, vals):
        if not _TABLE_CAPACITY_FIELDS & set(vals):
            return super().write(vals)
        floors = self.sudo().floor_id
        res = super().write(vals)
        notify_waitlist_floors(self.env, floors | self.sudo().floor_id)
        return res
