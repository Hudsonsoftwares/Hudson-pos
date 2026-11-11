# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import ast
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DmsFolderRule(models.Model):
    """Auto-assignment rule that routes documents from a business model
    to a specific DMS directory automatically.

    Rules are evaluated in sequence order (lowest first). The first matching
    rule wins and routes the document to its configured directory.
    """

    _name = "dms.folder.rule"
    _description = "DMS Folder Auto-Assignment Rule"
    _order = "sequence asc, name asc"

    name = fields.Char(
        string="Rule Name",
        required=True,
        help="Descriptive name for this auto-assignment rule.",
    )
    active = fields.Boolean(
        default=True,
        help="Inactive rules are not evaluated during auto-assignment.",
    )
    sequence = fields.Integer(
        default=10,
        help="Rules are evaluated in ascending sequence order. The first matching rule wins.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
        help="If set, this rule only applies to attachments from the given company.",
    )

    # ── Business Trigger Preset ───────────────────────────────────────────────
    trigger_type = fields.Selection(
        selection=[
            ("account_vendor_bill", "Vendor Bills (Accounting)"),
            ("account_customer_invoice", "Customer Invoices (Accounting)"),
            ("account_all", "All Accounting Entries (Accounting)"),
            ("sale_order", "Sales Orders & Quotations (Sales)"),
            ("purchase_order", "Purchase Orders & RFQs (Purchasing)"),
            ("hr_employee", "Employee Records (HR)"),
            ("hr_contract", "Employee Contracts (HR)"),
            ("hr_applicant", "Job Applicant CVs / Resumes (Recruitment)"),
            ("hr_expense", "Expenses & Receipts (HR)"),
            ("project_project", "Project Documents (Projects)"),
            ("project_task", "Task Attachments (Projects)"),
            ("helpdesk_ticket", "Ticket Attachments (Helpdesk)"),
            ("stock_picking", "Delivery & Receipt Notes (Inventory)"),
            ("res_partner", "Customer / Vendor Documents (Contacts)"),
            ("fleet_vehicle", "Vehicle Documents (Fleet)"),
            ("custom", "Custom Model..."),
        ],
        string="Document Type / Trigger",
        default="custom",
        required=True,
        help="Select a business trigger to automatically set up model, domain and target folder.",
    )

    # ── Source Model ─────────────────────────────────────────────────────────
    model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Apply On Model",
        required=True,
        ondelete="cascade",
        help="Odoo model whose attachments will be automatically routed.",
    )
    model_name = fields.Char(
        related="model_id.model",
        string="Model Technical Name",
        store=True,
        readonly=True,
    )
    domain = fields.Char(
        string="Filter Domain",
        default="[]",
        help="Optional domain expression to further filter which records trigger this rule. Example: [('state','=','done')]",
    )

    # ── Target Directory ─────────────────────────────────────────────────────
    directory_id = fields.Many2one(
        comodel_name="dms.directory",
        string="Target Folder",
        required=True,
        ondelete="restrict",
        help="DMS folder where matched documents will be routed.",
    )
    category_id = fields.Many2one(
        comodel_name="dms.category",
        string="Default Category",
        help="Category automatically assigned to documents routed by this rule.",
    )
    tag_ids = fields.Many2many(
        comodel_name="dms.tag",
        relation="dms_folder_rule_tag_rel",
        column1="rule_id",
        column2="tag_id",
        string="Default Tags",
        help="Tags automatically applied to documents routed by this rule.",
    )

    # ── Sub-folder Options ────────────────────────────────────────────────────
    create_subfolder = fields.Boolean(
        string="Create Per-Record Subfolder",
        default=False,
        help="When enabled, a subfolder named after the record is created inside the target folder (e.g. Accounting/Vendor Bills/BILL-2026-0001/).",
    )
    subfolder_name_field = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Subfolder Name Field",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['char','name','text'])]",
        help="Field from the source record used as the subfolder name. Defaults to display_name if not set.",
    )

    # ── Business Area Label ───────────────────────────────────────────────────
    area = fields.Selection(
        selection=[
            ("hr", "Human Resources"),
            ("recruitment", "Recruitment"),
            ("accounting", "Accounting"),
            ("sale", "Sales"),
            ("purchase", "Purchases"),
            ("product", "Products"),
            ("project", "Projects"),
            ("helpdesk", "Helpdesk"),
            ("approvals", "Approvals"),
            ("sign", "Sign"),
            ("fleet", "Fleet"),
            ("other", "Other"),
        ],
        string="Business Area",
        default="other",
        help="Business area this rule belongs to.",
    )

    # ── Computed ──────────────────────────────────────────────────────────────
    directory_path = fields.Char(
        related="directory_id.complete_name",
        string="Target Folder Path",
        readonly=True,
    )
    file_count = fields.Integer(
        string="Routed Files Count",
        compute="_compute_file_count",
    )

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        rules._backfill_record_folders()
        return rules

    def write(self, vals):
        res = super().write(vals)
        if vals.get("active") or "model_id" in vals:
            self._backfill_record_folders()
        return res

    def _backfill_record_folders(self):
        """When an employee rule is (re)activated, create the folders of
        employees that existed before and file their documents."""
        if any(r.active and r.model_name == "hr.employee" for r in self):
            Employee = self.env["hr.employee"].sudo()
            Employee._dms_backfill_folders()
            # Also file documents of employees that already had a folder
            # (route_attachment skips files already in the target folder).
            Employee.search([])._dms_route_existing_attachments()

    def _compute_file_count(self):
        for rec in self:
            if rec.model_name and rec.directory_id:
                rec.file_count = self.env["dms.file"].sudo().search_count([
                    ("res_model", "=", rec.model_name),
                    ("directory_id", "child_of", rec.directory_id.id),
                ])
            else:
                rec.file_count = 0

    @api.onchange("trigger_type")
    def _onchange_trigger_type(self):
        """Auto-populate model, domain, target directory and name when a preset trigger is selected."""
        if not self.trigger_type or self.trigger_type == "custom":
            return

        presets = {
            "account_vendor_bill": {
                "name": "Route Vendor Bills",
                "model": "account.move",
                "domain": "[('move_type', 'in', ('in_invoice', 'in_refund', 'in_receipt'))]",
                "area": "accounting",
                "folder_name": "Accounting",
                "create_subfolder": True,
            },
            "account_customer_invoice": {
                "name": "Route Customer Invoices",
                "model": "account.move",
                "domain": "[('move_type', 'in', ('out_invoice', 'out_refund', 'out_receipt'))]",
                "area": "accounting",
                "folder_name": "Accounting",
                "create_subfolder": True,
            },
            "account_all": {
                "name": "Route All Accounting Documents",
                "model": "account.move",
                "domain": "[]",
                "area": "accounting",
                "folder_name": "Accounting",
                "create_subfolder": False,
            },
            "sale_order": {
                "name": "Route Sales Orders & Quotations",
                "model": "sale.order",
                "domain": "[]",
                "area": "sale",
                "folder_name": "Sales",
                "create_subfolder": True,
            },
            "purchase_order": {
                "name": "Route Purchase Orders",
                "model": "purchase.order",
                "domain": "[]",
                "area": "purchase",
                "folder_name": "Purchases",
                "create_subfolder": True,
            },
            "hr_employee": {
                "name": "Route Employee Documents",
                "model": "hr.employee",
                "domain": "[]",
                "area": "hr",
                "folder_name": "Employees",
                "create_subfolder": True,
            },
            "hr_contract": {
                "name": "Route Employee Contracts",
                "model": "hr.contract",
                "domain": "[]",
                "area": "hr",
                "folder_name": "Employees",
                "create_subfolder": True,
            },
            "hr_applicant": {
                "name": "Route Job Applicant CVs / Resumes",
                "model": "hr.applicant",
                "domain": "[]",
                "area": "recruitment",
                "folder_name": "Recruitment",
                "create_subfolder": True,
            },
            "hr_expense": {
                "name": "Route Expenses & Receipts",
                "model": "hr.expense",
                "domain": "[]",
                "area": "hr",
                "folder_name": "Finance",
                "create_subfolder": False,
            },
            "project_project": {
                "name": "Route Project Documents",
                "model": "project.project",
                "domain": "[]",
                "area": "project",
                "folder_name": "Projects",
                "create_subfolder": True,
            },
            "project_task": {
                "name": "Route Task Attachments",
                "model": "project.task",
                "domain": "[]",
                "area": "project",
                "folder_name": "Projects",
                "create_subfolder": True,
            },
            "helpdesk_ticket": {
                "name": "Route Helpdesk Tickets",
                "model": "helpdesk.ticket",
                "domain": "[]",
                "area": "helpdesk",
                "folder_name": "Helpdesk",
                "create_subfolder": True,
            },
            "stock_picking": {
                "name": "Route Delivery & Receipt Notes",
                "model": "stock.picking",
                "domain": "[]",
                "area": "other",
                "folder_name": "Finance",
                "create_subfolder": False,
            },
            "res_partner": {
                "name": "Route Contact Documents",
                "model": "res.partner",
                "domain": "[]",
                "area": "other",
                "folder_name": "Finance",
                "create_subfolder": True,
            },
            "fleet_vehicle": {
                "name": "Route Vehicle Documents",
                "model": "fleet.vehicle",
                "domain": "[]",
                "area": "fleet",
                "folder_name": "Fleet",
                "create_subfolder": True,
            },
        }

        conf = presets.get(self.trigger_type)
        if conf:
            self.name = conf["name"]
            self.area = conf["area"]
            self.domain = conf["domain"]
            self.create_subfolder = conf["create_subfolder"]

            # Find model
            ir_model = self.env["ir.model"].sudo().search([("model", "=", conf["model"])], limit=1)
            if ir_model:
                self.model_id = ir_model.id

            # Find target directory
            folder = self.env["dms.directory"].sudo().search([
                ("name", "ilike", conf["folder_name"]),
                ("is_root_directory", "=", True),
            ], limit=1)
            if not folder:
                folder = self.env["dms.directory"].sudo().search([("name", "ilike", conf["folder_name"])], limit=1)
            if folder:
                self.directory_id = folder.id

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_open_directory(self):
        """Navigate to the target directory."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.directory_id.name,
            "res_model": "dms.directory",
            "res_id": self.directory_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_routed_files(self):
        """View all files routed to the target directory or created from this model."""
        self.ensure_one()
        return {
            "name": _("Routed Documents — %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "dms.file",
            "view_mode": "kanban,list,form",
            "domain": [
                ("res_model", "=", self.model_name),
                ("directory_id", "child_of", self.directory_id.id),
            ],
            "context": {"default_directory_id": self.directory_id.id},
        }

    def action_route_existing_attachments(self):
        """Retroactively route all historical attachments matching this rule into DMS."""
        self.ensure_one()
        if not self.model_name or self.model_name not in self.env:
            raise UserError(_("Please select a valid installed model first."))

        domain = []
        if self.domain and self.domain.strip() != "[]":
            try:
                domain = ast.literal_eval(self.domain)
            except Exception as e:
                raise UserError(_("Invalid filter domain syntax: %s") % e)

        # Search matching records in the source model
        matching_records = self.env[self.model_name].sudo().search(domain)
        if not matching_records:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No Matching Records"),
                    "message": _("No %s records match the configured domain filter.") % self.model_id.name,
                    "type": "warning",
                    "sticky": False,
                }
            }

        # Find attachments linked to these records
        attachments = self.env["ir.attachment"].sudo().search([
            ("res_model", "=", self.model_name),
            ("res_id", "in", matching_records.ids),
        ])

        count = 0
        for att in attachments:
            dms_file = self.route_attachment(att)
            if dms_file:
                count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Documents Routed"),
                "message": _("Processed %d attachment(s) into '%s'.") % (count, self.directory_id.complete_name or self.directory_id.name),
                "type": "success",
                "sticky": False,
            }
        }

    # ── Business Logic ────────────────────────────────────────────────────────
    def _evaluate_domain(self, record):
        """Return True if the record matches the rule's domain filter."""
        if not self.domain or self.domain.strip() == "[]":
            return True
        try:
            domain = ast.literal_eval(self.domain)
            return bool(self.env[self.model_name].sudo().search(
                [("id", "=", record.id)] + domain, limit=1
            ))
        except Exception:
            _logger.warning(
                "DMS Folder Rule '%s': could not evaluate domain '%s'",
                self.name,
                self.domain,
            )
            return True

    def _get_or_create_subfolder(self, record, parent_directory):
        """Find or create a per-record subfolder inside parent_directory."""
        if self.subfolder_name_field:
            field_name = self.subfolder_name_field.name
            subfolder_name = str(record[field_name] or record.display_name or "Unknown")
        else:
            subfolder_name = record.display_name or str(record.id)

        # Sanitise the name (max 255 chars, no slashes)
        subfolder_name = subfolder_name[:255].replace("/", "-").strip()

        # Look for existing subfolder
        existing = self.env["dms.directory"].sudo().search([
            ("parent_id", "=", parent_directory.id),
            ("name", "=", subfolder_name),
        ], limit=1)
        if existing:
            return existing

        # Create new subfolder
        # res_model/res_id link the folder to the record; dms.file's
        # res_model/res_id are related to its directory.
        return self.env["dms.directory"].sudo().with_context(check_name=False).create({
            "name": subfolder_name,
            "parent_id": parent_directory.id,
            "storage_id": parent_directory.storage_id.id,
            "res_model": record._name,
            "res_id": record.id,
        })

    @api.model
    def find_matching_rule(self, res_model, record=None):
        """Return the first active rule matching the given model (and record)."""
        domain = [
            ("model_name", "=", res_model),
            ("active", "=", True),
        ]
        company = False
        if record and "company_id" in record._fields and record.company_id:
            company = record.company_id
            domain.append(("company_id", "in", (False, company.id)))
        elif self.env.company:
            company = self.env.company
            domain.append(("company_id", "in", (False, company.id)))

        rules = self.sudo().search(domain, order="sequence asc, id asc")
        for rule in rules:
            if record is None or rule._evaluate_domain(record):
                return rule
        return self.browse()

    def route_attachment(self, attachment):
        """Route a single ir.attachment to the DMS directory configured in this rule."""
        self.ensure_one()
        if not self.env["ir.attachment"]._dms_is_routable(attachment):
            return False

        target_dir = self.directory_id

        # Company-specific target folder resolution if rule directory company differs from record company
        record = None
        if attachment.res_model in self.env:
            try:
                record = self.env[attachment.res_model].sudo().browse(attachment.res_id)
                if not record.exists():
                    record = None
            except Exception:
                record = None

        rec_company = False
        if record and "company_id" in record._fields and record.company_id:
            rec_company = record.company_id
        elif hasattr(attachment, "company_id") and attachment.company_id:
            rec_company = attachment.company_id

        if rec_company and target_dir and target_dir.company_id and target_dir.company_id != rec_company:
            matching_dir = self.env["dms.directory"].sudo().search([
                ("name", "=", target_dir.name),
                ("is_root_directory", "=", True),
                ("company_id", "=", rec_company.id),
            ], limit=1)
            if matching_dir:
                target_dir = matching_dir


        # Per-record subfolder
        if self.create_subfolder:
            try:
                record = self.env[attachment.res_model].sudo().browse(attachment.res_id)
                if record.exists():
                    # Records that manage their own DMS folder (hr.employee)
                    # must get it set up first; otherwise the rule creates a
                    # same-named sibling and the record's own setup then fails
                    # with "A directory with the same name already exists".
                    if (
                        "dms_directory_id" in record._fields
                        and not record.dms_directory_id
                        and hasattr(record, "_setup_dms_folder_and_permissions")
                    ):
                        record._setup_dms_folder_and_permissions()
                    if "dms_directory_id" in record._fields and record.dms_directory_id:
                        target_dir = record.dms_directory_id
                    else:
                        target_dir = self._get_or_create_subfolder(record, target_dir)
            except Exception as e:
                _logger.warning("DMS Folder Rule: could not create subfolder: %s", e)

        # Check if a DMS file already exists for this attachment
        existing_file = self.env["dms.file"].sudo().search([
            ("attachment_id", "=", attachment.id),
            ("directory_id", "=", target_dir.id),
        ], limit=1)
        if existing_file:
            return existing_file

        # Create the DMS file
        try:
            vals = {
                "name": attachment.name,
                "directory_id": target_dir.id,
                "attachment_id": attachment.id,
                "res_model": attachment.res_model,
                "res_id": attachment.res_id,
            }
            if self.tag_ids:
                vals["tag_ids"] = [(6, 0, self.tag_ids.ids)]
            if self.category_id:
                vals["category_id"] = self.category_id.id

            # Savepoint: a failure here must not abort the caller's
            # transaction (e.g. the employee/vehicle being saved).
            with self.env.cr.savepoint():
                dms_file = self.env["dms.file"].sudo().create(vals)
            _logger.info(
                "DMS: Routed attachment '%s' (id=%s) → folder '%s' via rule '%s'",
                attachment.name, attachment.id, target_dir.complete_name, self.name,
            )
            return dms_file
        except Exception as e:
            _logger.warning(
                "DMS Folder Rule '%s': failed to create dms.file for attachment %s: %s",
                self.name, attachment.id, e,
            )
            return False

    # ── Constraints ───────────────────────────────────────────────────────────
    @api.constrains("domain")
    def _check_domain(self):
        for rule in self:
            if rule.domain and rule.domain.strip() != "[]":
                try:
                    ast.literal_eval(rule.domain)
                except (ValueError, SyntaxError):
                    raise ValidationError(
                        _(
                            "Rule '%(name)s': domain '%(domain)s' is not a valid Python expression.",
                            name=rule.name,
                            domain=rule.domain,
                        )
                    )
