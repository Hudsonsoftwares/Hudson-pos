from odoo import api, fields, models

# Field types whose value can be auto-completed from / written back to a linked field
AUTOFILL_TYPES = ('text', 'multiline', 'selection', 'date')

LINKABLE_MODELS = ('res.partner', 'res.users')

TYPE_ICONS = {
    'signature': 'fa-pencil-square-o',
    'initial': 'fa-pencil-square-o',
    'text': 'fa-text-height',
    'multiline': 'fa-bars',
    'checkbox': 'fa-check-square-o',
    'radio': 'fa-dot-circle-o',
    'selection': 'fa-angle-down',
    'strikethrough': 'fa-strikethrough',
    'stamp': 'fa-pencil-square-o',
    'date': 'fa-calendar',
}

LINKED_FIELD_ICONS = {
    'name': 'fa-user-o',
    'email': 'fa-envelope-o',
    'phone': 'fa-phone',
    'mobile': 'fa-phone',
    'parent_id': 'fa-building-o',
    'company_name': 'fa-building-o',
    'commercial_company_name': 'fa-building-o',
}

# Default field names without a linked field that still deserve their own icon
NAME_ICONS = {
    'company': 'fa-building-o',
}


def split_options(options):
    """Choices of a selection field: one per line (legacy values are comma separated)."""
    if not options:
        return []
    separator = '\n' if '\n' in options else ','
    return [option.strip() for option in options.split(separator) if option.strip()]


class HudsonSignItemType(models.Model):
    _name = "hudson.sign.item.type"
    _description = "Signature Item Type"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Field Name", required=True)
    item_type = fields.Selection([
        ('signature', 'Signature'),
        ('initial', 'Initial'),
        ('text', 'Text'),
        ('multiline', 'Multiline Text'),
        ('checkbox', 'Checkbox'),
        ('radio', 'Radio'),
        ('selection', 'Selection'),
        ('strikethrough', 'Strikethrough'),
        ('stamp', 'Stamp'),
        ('date', 'Date'),
    ], string="Type", required=True, default='signature')

    linked_to = fields.Many2one(
        'ir.model', string="Linked to", ondelete='set null',
        domain=[('model', 'in', LINKABLE_MODELS)],
        help="Model of the signer record used to auto-complete this field.")
    linked_field = fields.Many2one(
        'ir.model.fields', string="Linked field", ondelete='set null',
        domain="[('model_id', '=', linked_to), ('store', '=', True), "
               "('ttype', 'in', ['char', 'text', 'selection', 'many2one', 'date', 'datetime', 'integer', 'float'])]")
    linked_field_name = fields.Char(related='linked_field.name', string="Linked field name")
    update_field = fields.Boolean(
        string="Update Field",
        help="Write the value entered by the signer back to the linked field.")

    placeholder = fields.Char(string="Placeholder")
    tip = fields.Char(string="Tip", help="Hint displayed in the signing hint")
    mandatory = fields.Boolean(string="Mandatory", default=True)
    is_read_only = fields.Boolean(string="Read Only")
    options = fields.Text(string="Options", help="Choices offered to the signer, one per line.")
    shared = fields.Boolean(
        string="Shared", default=True,
        help="Offer this field to other users in their field list. "
             "Unchecked, only its creator can use it.")
    user_ids = fields.Many2many(
        'res.users', string="Used by",
        help="Users offered this field. Leave empty to offer it to anyone.")

    @api.onchange('item_type')
    def _onchange_item_type(self):
        if self.item_type not in AUTOFILL_TYPES:
            self.linked_to = False
        if self.item_type in ('signature', 'initial'):
            self.is_read_only = False

    @api.onchange('linked_to')
    def _onchange_linked_to(self):
        if self.linked_field and self.linked_field.model_id != self.linked_to:
            self.linked_field = False
        if not self.linked_to:
            self.update_field = False

    @api.model
    def get_editor_tools(self):
        """Field palette shared by the template builder and the document signature editor."""
        return [{
            'key': f'type_{t.id}',
            'id': t.id,
            'type': t.item_type,
            'label': t.name,
            # ir.model.fields is only readable by administrators
            'icon': (LINKED_FIELD_ICONS.get(t.sudo().linked_field.name) or NAME_ICONS.get((t.name or '').lower())
                     or TYPE_ICONS.get(t.item_type, 'fa-pencil-square-o')),
            'placeholder': t.placeholder or t.name,
            'tip': t.tip or '',
            'mandatory': t.mandatory,
            'readonly': t.is_read_only,
            'options': '\n'.join(split_options(t.options)),
        } for t in self.search(self._get_editor_tools_domain())]

    @api.model
    def _get_editor_tools_domain(self):
        uid = self.env.uid
        return ['|', ('create_uid', '=', uid),
                '&', ('shared', '=', True), '|', ('user_ids', '=', False), ('user_ids', 'in', uid)]

    def _get_signer_record(self, user):
        self.ensure_one()
        if not user or not self.linked_field or self.linked_to.model not in LINKABLE_MODELS:
            return None
        return user.partner_id if self.linked_to.model == 'res.partner' else user

    def _get_autofill_value(self, user):
        """Return the linked field value of the signer as text, or False."""
        self.ensure_one()
        record = self._get_signer_record(user)
        if record is None:
            return False
        record = record.sudo()
        fname = self.linked_field.name
        if fname not in record._fields:
            return False
        value = record[fname]
        if not value:
            return False
        field = record._fields[fname]
        if field.type == 'many2one':
            return value.display_name
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value)
        return str(value)

    def _write_back_value(self, user, value):
        """Store the signer's answer on the linked field (``Update Field`` option)."""
        self.ensure_one()
        record = self._get_signer_record(user)
        if record is None or not self.update_field or not value:
            return
        fname = self.linked_field.name
        if fname in record._fields and record._fields[fname].type in ('char', 'text'):
            record.sudo().write({fname: value})
