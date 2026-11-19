# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""Never reset existing data while demo data loads.

Demo data is (re)loaded automatically whenever a module is installed (demo_autoloader.py). The
suites are written to be idempotent, but some of them also *update* records they find (a POS shop
named "Restaurant", the company, an appointment type...) and XML files loaded with mode='init'
write their values again on existing records. To guarantee that installing a module never resets
data that may have been modified by the user, every load runs inside ``protect_existing(env)``:

  * A record is *pre-existing* when it was created before the current install/upgrade run started
    (``create_date`` older than the first module loaded by this registry update). Records created
    during the run - by the demo itself or by the modules being installed - are not protected.
  * ``write`` / ``unlink`` called *directly by demo code* (this module's files) on pre-existing
    records are filtered: only fields that were added by the modules being installed in this run
    are written (they did not exist before, so nobody can have modified them), plus additive
    links of implied groups on ``res.groups`` (enables a feature, removes nothing). Everything else
    is skipped and logged; pre-existing records are never deleted.
  * Writes made by Odoo's own business logic (validating a transfer updates quants, confirming an
    order...) are not filtered, so stock and accounting stay consistent; demo code that would use
    such logic to change existing data (stock top-ups) checks ``preexisting()`` itself.
"""

import contextlib
import contextvars
import logging
import os
import sys

import odoo.orm
from odoo import api, models
from odoo.fields import Command

_logger = logging.getLogger(__name__)

_GUARD = contextvars.ContextVar('hudson_pos_demo_guard', default=None)

_MODULE_DIR = os.path.normcase(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_THIS_FILE = os.path.normcase(os.path.abspath(__file__))
_ODOO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(odoo.orm.__file__)))
# ORM plumbing between demo code and write(): field __set__, _load_records, convert_xml_import...
_CORE_PREFIXES = tuple(os.path.normcase(os.path.join(_ODOO_DIR, d)) for d in ('orm', 'api', 'fields', 'models', 'tools'))


class _GuardState:
    def __init__(self, env, run_start):
        self.env = env
        self.run_start = run_start
        self._new_fields = {}
        self._new_models = None
        self.skipped = {}
        self.missing_fields = set()

    def preexisting(self, records):
        if not records or not records._log_access or records._transient or records._abstract:
            return records.browse()
        ids = [i for i in records._ids if isinstance(i, int)]
        if not ids:
            return records.browse()
        records.env.cr.execute(
            f'SELECT id FROM "{records._table}" WHERE id = ANY(%s) AND create_date < %s',
            (ids, self.run_start))
        return records.browse([row[0] for row in records.env.cr.fetchall()])

    def new_fields(self, model):
        if model not in self._new_fields:
            self.env.cr.execute(
                "SELECT name FROM ir_model_fields WHERE model = %s AND create_date >= %s",
                (model, self.run_start))
            self._new_fields[model] = {row[0] for row in self.env.cr.fetchall()}
        return self._new_fields[model]

    def new_models(self):
        if self._new_models is None:
            self.env.cr.execute("SELECT model FROM ir_model WHERE create_date >= %s", (self.run_start,))
            self._new_models = {row[0] for row in self.env.cr.fetchall()}
        return self._new_models

    def allowed_vals(self, records, vals):
        new_fields = self.new_fields(records._name)
        allowed = {}
        for key, value in vals.items():
            if key in new_fields:
                allowed[key] = value
            elif records._name == 'res.groups' and _only_links(value):
                allowed[key] = value
        return allowed

    def skip(self, records, what):
        key = (records._name, what)
        self.skipped[key] = self.skipped.get(key, 0) + len(records)


def _only_links(value):
    if not isinstance(value, (list, tuple)) or not value:
        return False
    return all(isinstance(cmd, (list, tuple)) and cmd and cmd[0] == Command.LINK for cmd in value)


# write()/unlink() overrides of other modules (stock.picking.write, mail.thread.write...) sit between
# the caller and this override; they are passed through to find who really asked for the write.
_PASS_THROUGH = frozenset(('write', 'unlink'))
_CREATE_PASS_THROUGH = frozenset(('create',))


def _called_by_demo_code(pass_through=_PASS_THROUGH):
    """True when the first caller outside the ORM plumbing and the write/unlink override chain is a
    file of this module. A write made by Odoo business logic (action_confirm, _action_done, a create
    override...) is found first and is therefore not filtered, even when demo code called that logic."""
    frame = sys._getframe(2)
    while frame is not None:
        code = frame.f_code
        filename = os.path.normcase(os.path.abspath(code.co_filename))
        if not (filename == _THIS_FILE or code.co_name in pass_through or filename.startswith(_CORE_PREFIXES)):
            return filename.startswith(_MODULE_DIR)
        frame = frame.f_back
    return False


def run_start(env):
    """When the current install/upgrade run started (first module loaded by this registry update)."""
    modules = list(env.registry.updated_modules or ())
    if modules:
        env.cr.execute("SELECT MIN(write_date) FROM ir_module_module WHERE name = ANY(%s)", (modules,))
        row = env.cr.fetchone()
        if row and row[0]:
            return row[0]
    return env.cr.now()


@contextlib.contextmanager
def protect_existing(env):
    """Run demo loading without modifying or deleting records that existed before this run."""
    if _GUARD.get() is not None:  # nested call: the outer guard already applies
        yield _GUARD.get()
        return
    state = _GuardState(env, run_start(env))
    token = _GUARD.set(state)
    try:
        yield state
    finally:
        _GUARD.reset(token)
        if state.missing_fields:
            _logger.info("Hudson POS demo: values skipped for fields of apps not installed: %s",
                         ", ".join(sorted(state.missing_fields)))
        if state.skipped:
            _logger.info("Hudson POS demo: left existing data untouched: %s", ", ".join(
                f"{n} {what} on {model}" for (model, what), n in sorted(state.skipped.items())))


def guard_state():
    return _GUARD.get()


@contextlib.contextmanager
def unguarded():
    """For the loader's own bookkeeping (ir.config_parameter state) inside a guarded run."""
    token = _GUARD.set(None)
    try:
        yield
    finally:
        _GUARD.reset(token)


def preexisting(records):
    """Subset of ``records`` created before the current run (empty when no guard is active)."""
    state = _GUARD.get()
    return state.preexisting(records) if state else records.browse()


def _known_fields(state, records, vals):
    """Drop values of fields that do not exist (yet): the app adding them is not installed, e.g.
    'available_in_pos' without Point of Sale or 'is_storable' without Inventory. The demo record is
    created without that value instead of the whole demo step failing."""
    unknown = [key for key in vals if key not in records._fields]
    if not unknown:
        return vals
    for key in unknown:
        state.missing_fields.add(f"{records._name}.{key}")
    return {key: value for key, value in vals.items() if key in records._fields}


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model_create_multi
    def create(self, vals_list):
        state = _GUARD.get()
        if state is not None and _called_by_demo_code(_CREATE_PASS_THROUGH):
            vals_list = [_known_fields(state, self, vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        state = _GUARD.get()
        if state is None or not self or not _called_by_demo_code():
            return super().write(vals)
        vals = _known_fields(state, self, vals)
        old = state.preexisting(self)
        if not old:
            return super().write(vals)
        new = self - old
        if new:
            super(Base, new).write(vals)
        allowed = state.allowed_vals(old, vals)
        if allowed:
            super(Base, old).write(allowed)
        if set(vals) - set(allowed):
            state.skip(old, 'update(s)')
        return True

    def unlink(self):
        state = _GUARD.get()
        if state is None or not self or not _called_by_demo_code():
            return super().unlink()
        old = state.preexisting(self)
        if old:
            state.skip(old, 'deletion(s)')
        new = self - old
        return super(Base, new).unlink() if new else True
