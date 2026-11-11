# -*- coding: utf-8 -*-
import logging
import re
import psycopg2
from odoo.tools import config
from odoo.http import router

_logger = logging.getLogger(__name__)

# Preserve the true original function on the router module object itself
if not hasattr(router, '_original_set_session_and_dbname'):
    router._original_set_session_and_dbname = router._set_session_and_dbname


def _patched_set_session_and_dbname(request):
    try:
        router._original_set_session_and_dbname(request)
    except Exception as e:
        _logger.exception("Error in original _set_session_and_dbname: %s", e)

    try:
        if not getattr(request, 'db', None):
            host = request.httprequest.environ.get('HTTP_HOST')

            # 1. Check if ?db= was passed in query parameters
            db_param = request.httprequest.args.get('db')
            if db_param:
                valid_dbs = router.db_filter([db_param], host=host)
                if valid_dbs:
                    request.session.db = valid_dbs[0]
                    request.db = valid_dbs[0]
                    return

            # 2. Check if this is a DMS share or signature link without db specified
            path = request.httprequest.path or ''
            if '/dms/share/file/' in path or '/dms/signature/' in path:
                token = None
                if '/dms/share/file/' in path:
                    token_match = re.search(r'/dms/share/file/([a-zA-Z0-9_\-]+)', path)
                    if token_match:
                        t = token_match.group(1)
                        if t not in ('download', 'preview', 'replace'):
                            token = t
                elif '/dms/signature/' in path:
                    token_match = re.search(r'/dms/signature/\d+/([a-zA-Z0-9_\-]+)', path)
                    if token_match:
                        token = token_match.group(1)

                if token:
                    all_dbs = router.db_list(force=True, host=host)
                    db_user = config['db_user'] or 'odoo'
                    db_password = config['db_password'] or 'odoopwd'
                    db_host = config['db_host'] or 'localhost'
                    db_port = config['db_port'] or 5432
                    for candidate_db in all_dbs:
                        try:
                            conn = psycopg2.connect(
                                dbname=candidate_db,
                                user=db_user,
                                password=db_password,
                                host=db_host,
                                port=db_port,
                            )
                            with conn.cursor() as cur:
                                if '/dms/share/file/' in path:
                                    cur.execute("SELECT 1 FROM dms_file WHERE access_token = %s LIMIT 1", (token,))
                                else:
                                    cur.execute("SELECT 1 FROM dms_file_signature_request WHERE access_token = %s LIMIT 1", (token,))
                                found = cur.fetchone()
                            conn.close()
                            if found:
                                request.session.db = candidate_db
                                request.db = candidate_db
                                return
                        except Exception as e:
                            _logger.debug("Failed checking candidate db %s for token %s: %s", candidate_db, token, e)
    except Exception as e:
        _logger.exception("Error in DMS _patched_set_session_and_dbname: %s", e)


def apply_http_patch():
    if hasattr(router, '_set_session_and_dbname') and router._set_session_and_dbname != _patched_set_session_and_dbname:
        if not hasattr(router, '_original_set_session_and_dbname'):
            router._original_set_session_and_dbname = router._set_session_and_dbname
        router._set_session_and_dbname = _patched_set_session_and_dbname
        _logger.info("Successfully installed DMS _set_session_and_dbname router patch.")


apply_http_patch()
