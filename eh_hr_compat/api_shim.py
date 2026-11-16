# -*- coding: utf-8 -*-
"""Single source of truth for everything that differs between Odoo versions.

DO NOT import anything from elsewhere in the platform.  This file MUST be
importable before the Odoo registry is built (no env, no records, no models).
"""
from odoo import release

# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------
ODOO_VERSION = int(release.version_info[0])
IS_19_PLUS = ODOO_VERSION >= 19
IS_18_PLUS = ODOO_VERSION >= 18
IS_17_PLUS = ODOO_VERSION >= 17

# ---------------------------------------------------------------------------
# Model name shims
# ---------------------------------------------------------------------------
# The 18 → 19 rename ``hr.contract`` → ``hr.version`` is the single biggest
# breaking change for HR addons.  Use this constant instead of either literal.
CONTRACT_MODEL = 'hr.version' if IS_19_PLUS else 'hr.contract'


# ---------------------------------------------------------------------------
# Field attribute shims
# ---------------------------------------------------------------------------
def tracking(level=True):
    """Return the kwarg pair for tracking a field across versions.

    Odoo ≥ 13: ``tracking=True``
    Odoo  ≤ 12: ``track_visibility='onchange'``  (we no longer support 12, but
                we keep the shape so future regressions are caught.)

    Usage::

        state = fields.Selection(..., **tracking())
    """
    return {'tracking': level}


# ---------------------------------------------------------------------------
# View shims
# ---------------------------------------------------------------------------
def legacy_view_mode(modes):
    """Convert a comma-separated view-mode string to the right vocabulary.

    Odoo 17+ renamed the tree view to ``list`` in action view_mode strings.
    Trunk uses ``list``; older versions need ``tree``.

    >>> legacy_view_mode("list,form,kanban")  # on 19
    'list,form,kanban'
    >>> legacy_view_mode("list,form,kanban")  # on 16 (conceptually)
    'tree,form,kanban'
    """
    if IS_17_PLUS:
        return modes
    return modes.replace('list', 'tree')


# ---------------------------------------------------------------------------
# OWL import path
# ---------------------------------------------------------------------------
def owl_import_path():
    """Return the canonical OWL import path string for the running version.

    Used by the build-time backport transformer when rewriting JS sources.
    The Python side rarely needs this - but exposing it keeps the surface
    symmetric.
    """
    return '@odoo/owl'


# ---------------------------------------------------------------------------
# Field-rename helper for migrations
# ---------------------------------------------------------------------------
def safe_field_rename(cr, table, old, new):
    """Idempotent column rename in pre-migrate scripts.

    Renames ``old`` to ``new`` only if ``old`` exists and ``new`` does not.
    Avoids the OpenHRMS bug where renames silently dropped data on upgrade.
    """
    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s AND column_name IN (%s, %s)",
        (table, old, new),
    )
    cols = {r[0] for r in cr.fetchall()}
    if old in cols and new not in cols:
        cr.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}"')
        return True
    return False


# ---------------------------------------------------------------------------
# res.users groups field: group_ids on Odoo 19+, groups_id on 16 to 18
# ---------------------------------------------------------------------------
def user_groups(user):
    """Return a user's security-groups recordset across Odoo versions.

    Odoo 19 renamed res.users.groups_id to group_ids. Platform code calls this
    instead of touching either name directly, so it runs on 16 to 19.
    """
    field = 'group_ids' if 'group_ids' in user._fields else 'groups_id'
    return user[field]


def group_users(group):
    """Return a security group's member users recordset across Odoo versions.

    Odoo 19 renamed res.groups.users to res.groups.user_ids (the inverse of the
    res.users.groups_id -> group_ids rename). Platform code calls this instead
    of touching either name directly, so it runs on 16 to 19.
    """
    field = 'user_ids' if 'user_ids' in group._fields else 'users'
    return group[field]


def setup_access_dropdown(env, name, sequence, group_xmlids):
    """Render a group hierarchy as a single exclusive dropdown on the user form
    (the standard "access level" selector) instead of independent checkboxes.

    Version-portable, because the categorisation field moved:
      * Odoo 16 to 18: the groups share an ir.module.category, set on
        ``res.groups.category_id``.
      * Odoo 19+: ``category_id`` was removed from res.groups; groups share a
        ``res.groups.privilege`` (``res.groups.privilege_id``) which itself
        carries the category.

    The groups must form an implication chain (employee -> manager -> officer ->
    admin) for Odoo to present them as ordered, mutually exclusive levels.
    Records are looked up by name so the helper is idempotent across re-installs.
    """
    groups = [env.ref(x, raise_if_not_found=False) for x in group_xmlids]
    groups = [g for g in groups if g]
    if not groups:
        return
    fields_ = env['res.groups']._fields
    if 'privilege_id' in fields_:
        Cat = env['ir.module.category']
        cat = Cat.search([('name', '=', 'HR Platform')], limit=1) \
            or Cat.sudo().create({'name': 'HR Platform', 'sequence': 5})
        Priv = env['res.groups.privilege']
        priv = Priv.search([('name', '=', name)], limit=1) \
            or Priv.sudo().create(
                {'name': name, 'sequence': sequence, 'category_id': cat.id})
        groups_recs = groups[0].browse([g.id for g in groups])
        groups_recs.sudo().write({'privilege_id': priv.id})
    elif 'category_id' in fields_:
        Cat = env['ir.module.category']
        cat = Cat.search([('name', '=', name)], limit=1) \
            or Cat.sudo().create({'name': name, 'sequence': sequence})
        groups[0].browse([g.id for g in groups]).sudo().write(
            {'category_id': cat.id})


def groups_field(env_or_model):
    """Return the res.users groups field NAME for the running version.

    Use this when BUILDING create/write vals that assign security groups, where
    a literal dict key is required and the read helper user_groups() cannot be
    used::

        gf = groups_field(env)
        env['res.users'].create({'login': 'x', gf: [(4, group.id)]})

    'group_ids' on Odoo 19+, 'groups_id' on 16 to 18. Accepts an Environment or
    any recordset.
    """
    env = getattr(env_or_model, 'env', env_or_model)
    return 'group_ids' if 'group_ids' in env['res.users']._fields else 'groups_id'
