# -*- coding: utf-8 -*-
"""
Diagnostic trace for multi-company menu issues.

OFF by default. Turn it on with the system parameter
``hudson_kitchen_terms.trace`` = ``1`` (Settings > Technical > System
Parameters), reproduce the problem, then read the lines in
Settings > Technical > Logging, filtered on Name = ``hudson.kitchen.trace``.

Each line is written with its own cursor, so it survives even when the
request itself fails and rolls back (or runs on a read-only cursor, like
/web/webclient/load_menus does).
"""
import inspect
import logging
import traceback

_logger = logging.getLogger(__name__)

TRACE_PARAM = 'hudson_kitchen_terms.trace'
TRACE_NAME = 'hudson.kitchen.trace'


def trace_enabled(env):
    try:
        return env['ir.config_parameter'].sudo().get_param(TRACE_PARAM, '0') in ('1', 'True', 'true')
    except Exception:
        return False


def _company_snapshot(env, company=None):
    """Everything that decides which company's menus a user gets."""
    data = {}
    try:
        from odoo.http import request
        if request:
            data['path'] = getattr(request.httprequest, 'path', None)
            data['cookie_cids'] = request.cookies.get('cids')
            data['request_ctx_cids'] = (request.context or {}).get('allowed_company_ids')
    except Exception:
        pass
    user = env.user
    data['uid'] = env.uid
    data['login'] = user.login
    data['env_ctx_cids'] = env.context.get('allowed_company_ids')
    data['env_company'] = f'{env.company.id}:{env.company.name}'
    data['user_default_company'] = f'{user.company_id.id}:{user.company_id.name}'
    data['user_allowed_companies'] = user.company_ids.ids
    if company is not None:
        data['resolved_company'] = f'{company.id}:{company.name}' if company else False
        data['kitchen_mode'] = bool(company.kitchen_mode) if company else None
        data['kitchen_task'] = bool(company.kitchen_task) if company else None
    routing = env.ref('mrp.group_mrp_routings', raise_if_not_found=False)
    if routing:
        data['user_has_routing_group'] = routing.id in user._get_group_ids()
    return data


def kitchen_trace(env, event, level='INFO', company=None, exc=False, stack=False, force=False, **extra):
    """Write one trace line to ir_logging when the trace is enabled.

    stack=True appends the Python call stack (who called this code);
    force=True writes even when the trace switch is off.
    """
    if not force and not trace_enabled(env):
        return
    try:
        data = _company_snapshot(env, company)
        data.update(extra)
        message = f'[{event}] ' + ' | '.join(f'{k}={v}' for k, v in data.items())
        if exc:
            message += '\n' + traceback.format_exc()
        if stack:
            message += '\nCALLED FROM:\n' + ''.join(traceback.format_stack()[:-1])
        frame = inspect.stack()[1]
        with env.registry.cursor() as cr:
            cr.execute(
                """
                INSERT INTO ir_logging
                    (create_date, create_uid, type, dbname, name, level,
                     message, path, func, line)
                VALUES (NOW() AT TIME ZONE 'UTC', %s, 'server', %s, %s, %s,
                        %s, %s, %s, %s)
                """,
                (env.uid, cr.dbname, TRACE_NAME, level, message,
                 frame.filename, f'{event} ({frame.function})', str(frame.lineno)),
            )
    except Exception:
        # Tracing must never break the real request.
        _logger.exception('kitchen_trace failed for event %s', event)
