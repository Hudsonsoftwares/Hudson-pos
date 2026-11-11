# Copyright 2017-2019 MuK IT GmbH
# Copyright 2026 Tecnativa - Víctor Martínez
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
import json
import unicodedata

from odoo import _, http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.web.controllers.binary import clean


class OnboardingController(http.Controller):
    @http.route("/config/dms.forbidden_extensions", type="json", auth="user")
    def forbidden_extensions(self, **_kwargs):
        params = request.env["ir.config_parameter"].sudo()
        return {
            "forbidden_extensions": params.get_param(
                "dms.forbidden_extensions", default=""
            )
        }

    @http.route("/web/binary/upload_dms_file", type="http", auth="user")
    def upload_dms_file(self, ufile, directory_id, callback=None, **kwargs):
        try:
            directory_id = int(directory_id)
            files = request.httprequest.files.getlist("ufile")
            Model = request.env["dms.file"]
            out = """<script language="javascript" type="text/javascript">
                        var win = window.top.window;
                        win.jQuery(win).trigger(%s, %s);
                    </script>"""
            args = []
            for ufile_item in files:
                filename = ufile_item.filename
                if request.httprequest.user_agent.browser == "safari":
                    filename = unicodedata.normalize("NFD", ufile_item.filename)
                try:
                    from odoo.tools.binary import BinaryBytes
                    dms_file = Model.create(
                        {
                            "directory_id": directory_id,
                            "name": filename,
                            "content_binary": BinaryBytes(ufile_item.read()),
                        }
                    )
                except AccessError:
                    args.append({"error": _("You are not allowed to upload a file here.")})
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).exception("Failed to upload DMS file")
                    args.append({"error": _("File upload failed: %s") % str(e)})
                else:
                    args.append(
                        {
                            "filename": clean(filename),
                            "mimetype": dms_file.mimetype,
                            "id": dms_file.id,
                            "size": dms_file.size,
                        }
                    )
            return (
                out % (json.dumps(clean(callback)), json.dumps(args))
                if callback
                else json.dumps(args)
            )
        except Exception as global_e:
            import traceback
            return json.dumps([{"error": "GLOBAL CRASH: " + str(global_e) + "\n" + traceback.format_exc()}])
