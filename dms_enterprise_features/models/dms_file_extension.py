# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# System-level forbidden file extensions permanently blocked in Document Controller
# (Executables, installer packages, scripts, system binaries, and dangerous formats)
SYSTEM_FORBIDDEN_EXTENSIONS = {
    # Windows executables & binaries
    "exe", "msi", "msp", "com", "scr", "pif", "gadget", "hta", "cpl",
    # Script formats
    "bat", "cmd", "vbs", "vbe", "wsf", "wsh", "ps1", "ps1xml", "ps2", "ps2xml", "psc1", "psc2", "reg",
    # Linux / Unix / macOS binaries & scripts
    "sh", "bash", "zsh", "csh", "ksh", "app", "bin", "deb", "rpm", "pkg", "dmg",
    # Dynamic libraries and system modules
    "dll", "sys", "drv", "so", "dylib", "ocx",
    # Mobile app packages and runnable archives
    "apk", "xapk", "ipa", "jar",
}


class DmsFileExtension(models.Model):
    _name = "dms.file.extension"
    _description = "Document File Extension"
    _order = "category, name"
    _rec_name = "name"

    name = fields.Char(string="Extension", required=True, index=True)
    description = fields.Char(string="Format / Description")
    category = fields.Selection([
        ("spreadsheet", "Spreadsheets / Tabular"),
        ("document", "Documents & Text"),
        ("presentation", "Presentations"),
        ("image", "Images & Graphics"),
        ("video", "Videos"),
        ("audio", "Audio"),
        ("archive", "Archives & Compressed"),
        ("code", "Code & Data"),
        ("other", "Other"),
    ], string="Category", default="document")
    color = fields.Integer(string="Color Index", default=0)

    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
        store=True,
    )

    @api.depends("name", "description")
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.description:
                rec.display_name = f".{rec.name} — {rec.description}"
            elif rec.name:
                rec.display_name = f".{rec.name}"
            else:
                rec.display_name = ""

    @api.constrains("name")
    def _check_name(self):
        for rec in self:
            if not rec.name:
                continue
            normalized = rec.name.strip().lower().lstrip(".")
            if normalized in SYSTEM_FORBIDDEN_EXTENSIONS:
                raise ValidationError(
                    _(
                        "The file extension '.%s' is an executable or system binary format "
                        "and is already permanently blocked by default in Document Controller."
                    )
                    % normalized
                )
            duplicate = self.search([
                ("id", "!=", rec.id),
                ("name", "=", normalized),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    _("The file extension '%s' already exists in the system.") % normalized
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name"):
                vals["name"] = vals["name"].strip().lower().lstrip(".")
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("name"):
            vals["name"] = vals["name"].strip().lower().lstrip(".")
        return super().write(vals)

    @api.model
    def name_create(self, name):
        """Allow quick creation from Many2many dropdown tags widget."""
        clean_name = name.strip().lower().lstrip(".")
        if clean_name in SYSTEM_FORBIDDEN_EXTENSIONS:
            raise ValidationError(
                _(
                    "The file extension '.%s' is an executable/system file and is permanently blocked by default."
                )
                % clean_name
            )
        existing = self.search([("name", "=", clean_name)], limit=1)
        if existing:
            return existing.id, existing.display_name
        record = self.create({
            "name": clean_name,
            "description": f"{clean_name.upper()} File",
            "category": "document",
        })
        return record.id, record.display_name

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = list(domain or [])
        if name:
            clean_name = name.strip().lower().lstrip(".")
            name_domain = [
                '|', '|', '|',
                ('name', operator, clean_name),
                ('display_name', operator, name),
                ('description', operator, name),
                ('category', operator, name),
            ]
            domain = name_domain + domain
        return super()._name_search(name, domain=domain, operator=operator, limit=limit, order=order)
