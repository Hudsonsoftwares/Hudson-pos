# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""Load demo XML files against whatever apps are installed right now.

``load_demo_xml`` is a drop-in replacement for ``odoo.tools.convert_file`` that first removes
from the XML document:
  * ``<record>`` nodes whose model is not in the registry (app not installed), and
  * ``<field>`` nodes whose field does not exist on the model (provided by an app that is not
    installed, e.g. ``website_menu`` on events needs Website Events, ``website_track`` needs
    Event Tracks).

So a file loads as far as possible instead of failing as a whole. Files are loaded with
``mode='init'``, which writes the XML values again on records that already exist; when the app
providing a stripped field is installed later, the auto-loader (demo_autoloader.py) re-runs the
suite - ``xml_probes`` lists every model/field a file uses for that purpose - and the field is
filled in on the existing records.
"""

import functools
import io
import json
import logging
import os

from lxml import etree

from odoo.tools.convert import convert_xml_import

from .demo_guard import guard_state, unguarded, set_param

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
MODULE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class _NamedBytesIO(io.BytesIO):
    """convert_xml_import reads ``xmlfile.name`` for logging and the install_filename context."""

    def __init__(self, data, name):
        super().__init__(data)
        self.name = name


def _iter_records(root):
    for rec in root.iter('record'):
        model = rec.get('model')
        if model:
            yield rec, model


def _filter_document(env, root):
    """Remove records of missing models, fields missing on their model, and references to uninstalled modules.
    Returns what was removed."""
    dropped_records, dropped_fields = [], []
    for rec, model in list(_iter_records(root)):
        if model not in env.registry:
            parent = rec.getparent()
            if parent is not None:
                parent.remove(rec)
                dropped_records.append(f"{model}:{rec.get('id', '?')}")
    for rec, model in _iter_records(root):
        fields = env[model]._fields
        for field in list(rec.findall('field')):
            name = field.get('name')
            if name and name not in fields:
                rec.remove(field)
                dropped_fields.append(f"{model}.{name}")
                continue
            ref = field.get('ref')
            if ref and '.' in ref and not ref.startswith(f"{MODULE}."):
                if not env.ref(ref, raise_if_not_found=False):
                    rec.remove(field)
                    dropped_fields.append(f"{model}.{name} (missing ref: {ref})")
    return dropped_records, sorted(set(dropped_fields))


LOADED_PARAM = 'hudson_pos_demo_data.loaded_xml_records'


def _own_xml_name(rec_id):
    """Name of the xmlid of this module for a record id of a demo file (None for other modules')."""
    if not rec_id:
        return None
    module, dot, name = rec_id.partition('.')
    if not dot:
        return rec_id
    return name if module == MODULE else None


def _loaded_records(env):
    env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (LOADED_PARAM,))
    row = env.cr.fetchone()
    try:
        return json.loads(row[0]) if row and row[0] else {}
    except ValueError:
        return {}


def _existing_names(env, names):
    if not names:
        return set()
    env.cr.execute("SELECT name FROM ir_model_data WHERE module = %s AND name = ANY(%s)", (MODULE, list(names)))
    return {row[0] for row in env.cr.fetchall()}


def _drop_deleted_records(env, root, xml_file, state):
    """Records this file loaded before that no longer exist were deleted by the user: keep them
    deleted (unless their model was only installed now). Records never loaded are created."""
    names = {n for n in (_own_xml_name(r.get('id')) for r, _m in _iter_records(root)) if n}
    existing = _existing_names(env, names)
    if getattr(state, 'force', False):
        return names, existing, []
    loaded_before = set(_loaded_records(env).get(xml_file, ())) | existing
    new_models = state.new_models()
    dropped = []
    for rec, model in list(_iter_records(root)):
        name = _own_xml_name(rec.get('id'))
        if name and name in loaded_before and name not in existing and model not in new_models:
            parent = rec.getparent()
            if parent is not None:
                parent.remove(rec)
                dropped.append(name)
    return names, loaded_before, dropped


def _remember_loaded(env, xml_file, names):
    data = _loaded_records(env)
    data[xml_file] = sorted(set(data.get(xml_file, ())) | set(names))
    with unguarded():
        set_param(env, LOADED_PARAM, json.dumps(data))


def load_demo_xml(env, module, xml_file, idref=None, mode='init', noupdate=True, **_kwargs):
    """Like ``convert_file`` but tolerant of apps that are not installed (see module docstring).

    Inside a guarded run (demo_guard.protect_existing) existing records only get the fields added
    by the modules being installed, and demo records the user deleted are not created again."""
    pathname = os.path.join(MODULE_PATH, xml_file)
    root = etree.parse(pathname).getroot()
    state = guard_state()
    names = loaded_before = None
    if state is not None:
        names, loaded_before, deleted = _drop_deleted_records(env, root, xml_file, state)
        if deleted:
            _logger.info("Hudson POS demo: %s - not recreating %s record(s) deleted by the user: %s",
                         xml_file, len(deleted), ', '.join(deleted[:5]) + (', ...' if len(deleted) > 5 else ''))
    dropped_records, dropped_fields = _filter_document(env, root)
    if dropped_records or dropped_fields:
        _logger.info(
            "Hudson POS demo: %s - skipped %s record(s) of apps not installed%s; fields not available yet: %s",
            xml_file, len(dropped_records),
            f" ({', '.join(dropped_records[:5])}{', ...' if len(dropped_records) > 5 else ''})" if dropped_records else '',
            ', '.join(dropped_fields) or 'none',
        )
    data = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    convert_xml_import(env, module or MODULE, _NamedBytesIO(data, pathname),
                       idref if idref is not None else {}, mode, noupdate)
    if state is not None:
        # remember what this file created, so that a later deletion by the user is respected
        _remember_loaded(env, xml_file, _existing_names(env, names) | loaded_before)


@functools.cache
def xml_probes(*xml_files):
    """Every ``model`` and ``model/field`` used by the given demo files (auto-loader probes)."""
    probes = set()
    for xml_file in xml_files:
        pathname = os.path.join(MODULE_PATH, xml_file)
        try:
            root = etree.parse(pathname).getroot()
        except (OSError, etree.XMLSyntaxError) as e:
            _logger.warning("Hudson POS demo: cannot read %s: %s", xml_file, e)
            continue
        for rec, model in _iter_records(root):
            probes.add(model)
            for field in rec.findall('field'):
                if field.get('name'):
                    probes.add(f"{model}/{field.get('name')}")
    return tuple(sorted(probes))
