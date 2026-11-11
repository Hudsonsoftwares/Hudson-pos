# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from . import http_patch
from . import models
from . import wizard
from . import controllers


def post_init_hook(env):
    """Create default dms.folder.rule records for each business area.

    We do this in Python rather than XML so we can safely skip models that
    are not installed in the current Odoo instance (e.g., if sign, approvals,
    or project are not installed, we just skip those rules).
    """
    _create_default_rules(env)


def _create_default_rules(env):
    """Create auto-assignment rules for installed business models with trigger presets."""
    IcpParam = env["ir.config_parameter"].sudo()
    FolderRule = env["dms.folder.rule"].sudo()
    IrModel = env["ir.model"].sudo()
    Directory = env["dms.directory"].sudo()

    # Rule definitions: (trigger_type, name, model_name, domain, folder_name, folder_param, area, create_sub, seq)
    default_rules = [
        ("account_vendor_bill", "Route Vendor Bills", "account.move", "[('move_type', 'in', ('in_invoice', 'in_refund', 'in_receipt'))]", "Accounting", "dms_enterprise.accounting_folder_id", "accounting", True, 10),
        ("account_customer_invoice", "Route Customer Invoices", "account.move", "[('move_type', 'in', ('out_invoice', 'out_refund', 'out_receipt'))]", "Accounting", "dms_enterprise.accounting_folder_id", "accounting", True, 11),
        ("sale_order", "Route Sales Orders & Quotations", "sale.order", "[]", "Sales", "dms_enterprise.sale_folder_id", "sale", True, 20),
        ("purchase_order", "Route Purchase Orders", "purchase.order", "[]", "Purchases", "dms_enterprise.purchase_folder_id", "purchase", True, 25),
        ("hr_employee", "Route Employee Documents", "hr.employee", "[]", "Employees", "dms_enterprise.hr_folder_id", "hr", True, 30),
        ("hr_contract", "Route Employee Contracts", "hr.contract", "[]", "Employees", "dms_enterprise.hr_folder_id", "hr", True, 35),
        ("hr_applicant", "Route Job Applicant CVs / Resumes", "hr.applicant", "[]", "Recruitment", "dms_enterprise.recruitment_folder_id", "recruitment", True, 40),
        ("project_project", "Route Project Documents", "project.project", "[]", "Projects", "dms_enterprise.project_folder_id", "project", True, 50),
        ("project_task", "Route Task Attachments", "project.task", "[]", "Projects", "dms_enterprise.project_folder_id", "project", True, 55),
        ("helpdesk_ticket", "Route Helpdesk Tickets", "helpdesk.ticket", "[]", "Helpdesk", "dms_enterprise.helpdesk_folder_id", "helpdesk", True, 60),
        ("fleet_vehicle", "Route Vehicle Documents", "fleet.vehicle", "[]", "Fleet", "dms_enterprise.fleet_folder_id", "fleet", True, 70),
    ]

    for trigger_type, name, model_name, domain_expr, folder_name, folder_param, area, create_sub, seq in default_rules:
        ir_model = IrModel.search([("model", "=", model_name)], limit=1)
        if not ir_model:
            continue

        # Look up folder from param first, then by name
        folder = None
        get_param_fn = getattr(IcpParam, "get_str", getattr(IcpParam, "get_param", lambda k, d="": d))
        folder_id_str = get_param_fn(folder_param, "")
        if folder_id_str:
            try:
                folder = Directory.browse(int(folder_id_str))
                if not folder.exists():
                    folder = None
            except (ValueError, TypeError):
                folder = None

        if not folder:
            folder = Directory.search([("name", "ilike", folder_name), ("is_root_directory", "=", True)], limit=1)
        if not folder:
            folder = Directory.search([("name", "ilike", folder_name)], limit=1)

        if not folder:
            continue

        existing = FolderRule.search([
            ("model_id", "=", ir_model.id),
            ("name", "=", name),
        ], limit=1)
        if existing:
            continue

        FolderRule.create({
            "name": name,
            "trigger_type": trigger_type,
            "area": area,
            "model_id": ir_model.id,
            "domain": domain_expr,
            "directory_id": folder.id,
            "create_subfolder": create_sub,
            "active": True,
            "sequence": seq,
        })
