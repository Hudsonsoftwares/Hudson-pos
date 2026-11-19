# -*- coding: utf-8 -*-
import copy
import logging
import re
from lxml import etree

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class KitchenLabel(models.Model):
    _name = 'kitchen.label'
    _description = 'Kitchen Mode Terminology Mapping'
    _order = 'sequence, id'

    name = fields.Char(
        string="Standard Label",
        required=True,
        index=True,
        help="The standard Odoo terminology to be replaced (e.g., Bills of Materials)."
    )
    kitchen_label = fields.Char(
        string="Kitchen Label",
        required=True,
        help="The restaurant/kitchen terminology to display (e.g., Recipes)."
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Used to order mappings in the view."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to deactivate this terminology mapping without deleting it."
    )
    category = fields.Selection(
        selection=[
            ('mrp', 'Manufacturing'),
            ('quality', 'Quality'),
            ('maintenance', 'Maintenance'),
            ('plm', 'PLM'),
            ('other', 'Other'),
        ],
        string="Category",
        default='mrp',
        required=True,
        help="Category or module associated with this term."
    )
    notes = fields.Text(
        string="Notes",
        help="Optional notes or context about this terminology mapping."
    )

    @api.model
    def _invalidate_terminology_caches(self):
        """
        Invalidate all ormcaches and registry caches so changes take effect
        immediately upon page reload.
        """
        try:
            if hasattr(self.env, 'transaction') and hasattr(self.env.transaction, 'invalidate_ormcache'):
                self.env.transaction.invalidate_ormcache('stable')
                self.env.transaction.invalidate_ormcache('default')
            self.env.invalidate_all()
            if hasattr(self.env.registry, '_signal_changes'):
                try:
                    self.env.registry._signal_changes(self.env.cr, ['default', 'stable'])
                except Exception:
                    pass
            if hasattr(self.env.registry, 'clear_cache'):
                self.env.registry.clear_cache()
            _logger.info("Kitchen terminology caches successfully invalidated.")
        except Exception as e:
            _logger.warning("Error invalidating terminology caches: %s", e)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._invalidate_terminology_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._invalidate_terminology_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self._invalidate_terminology_caches()
        return res

    @api.model
    def get_terms_mapping(self):
        """
        Returns active terms mapping as a list of tuples:
        [(standard_label, kitchen_label), ...]
        Sorted by length of standard_label descending so compound phrases
        are replaced before shorter substrings.
        """
        records = self.sudo().search([('active', '=', True)], order='sequence, id')
        terms = [
            (r.name.strip(), r.kitchen_label.strip())
            for r in records
            if r.name and r.kitchen_label
        ]
        # Sort by length descending to ensure longer phrases match first
        terms.sort(key=lambda item: len(item[0]), reverse=True)
        return terms

    @api.model
    def get_terms_dict(self):
        """
        Returns active terms as a dict: {standard_label: kitchen_label, ...}
        for use in the web client frontend session.
        """
        mapping = self.get_terms_mapping()
        return {std: kitch for std, kitch in mapping}

    @api.model
    def apply_terms_to_text(self, text, terms=None):
        """
        Replaces standard terms with kitchen terms in text while preserving casing.
        """
        if not text or not isinstance(text, str):
            return text
        if terms is None:
            terms = self.get_terms_mapping()
        if not terms:
            return text

        for old_term, new_term in terms:
            left = r'\b' if old_term[0].isalnum() else r'(?:\A|\s)'
            right = r'\b' if old_term[-1].isalnum() else r'(?:\Z|\s)'
            pattern = re.compile(left + re.escape(old_term) + right, re.IGNORECASE)

            def repl(match):
                matched = match.group(0)
                if matched.isupper():
                    return new_term.upper()
                elif matched.islower():
                    return new_term.lower()
                elif matched.istitle():
                    return new_term.title()
                return new_term

            text = pattern.sub(repl, text)
        return text

    @api.model
    def apply_terms_to_arch(self, arch_str, terms=None):
        """
        Parses XML arch and transforms visible presentation attributes
        (string, title, placeholder, help, confirm, sum, avg) and text content
        without touching any technical attributes (name, model, domain, context, etc.).
        """
        if not arch_str or not isinstance(arch_str, str):
            return arch_str
        if terms is None:
            terms = self.get_terms_mapping()
        if not terms:
            return arch_str

        try:
            root = etree.fromstring(arch_str.encode('utf-8'))
        except Exception:
            return arch_str

        target_attrs = {'string', 'title', 'placeholder', 'help', 'confirm', 'sum', 'avg'}

        for elem in root.iter():
            for attr in target_attrs:
                if attr in elem.attrib and elem.attrib[attr]:
                    elem.attrib[attr] = self.apply_terms_to_text(elem.attrib[attr], terms)
            if elem.text and elem.text.strip():
                elem.text = self.apply_terms_to_text(elem.text, terms)
            if elem.tail and elem.tail.strip():
                elem.tail = self.apply_terms_to_text(elem.tail, terms)

        return etree.tostring(root, encoding='unicode')

    @api.model
    def apply_terms_to_menus(self, menus_dict):
        """
        Transforms visible menu titles in menus_dict returned by ir.ui.menu.load_menus().
        """
        if not menus_dict or not isinstance(menus_dict, dict):
            return menus_dict
        terms = self.get_terms_mapping()
        if not terms:
            return menus_dict

        menus_copy = copy.deepcopy(menus_dict)
        for menu_id, menu in menus_copy.items():
            if isinstance(menu, dict) and menu.get('name') and isinstance(menu['name'], str):
                menu['name'] = self.apply_terms_to_text(menu['name'], terms)
        return menus_copy

    @api.model
    def apply_terms_to_action_dict(self, action_dict):
        """
        Transforms action names, display_names, and help in action dicts
        returned to the web client.
        """
        if not action_dict or not isinstance(action_dict, dict):
            return action_dict
        terms = self.get_terms_mapping()
        if not terms:
            return action_dict

        res = dict(action_dict)
        for key in ('name', 'display_name', 'help'):
            if key in res and isinstance(res[key], str):
                res[key] = self.apply_terms_to_text(res[key], terms)
        return res

    @api.model
    def apply_terms_to_views_result(self, views_result):
        """
        Transforms views architecture and model fields descriptions in
        the result returned by Base.get_views().
        """
        if not views_result or not isinstance(views_result, dict):
            return views_result
        terms = self.get_terms_mapping()
        if not terms:
            return views_result

        # Process views arch
        views = views_result.get('views')
        if isinstance(views, dict):
            for v_type, v_info in views.items():
                if isinstance(v_info, dict) and 'arch' in v_info and isinstance(v_info['arch'], str):
                    v_info['arch'] = self.apply_terms_to_arch(v_info['arch'], terms)

        # Process model fields
        models_dict = views_result.get('models')
        if isinstance(models_dict, dict):
            for model_name, m_info in models_dict.items():
                if isinstance(m_info, dict) and 'fields' in m_info and isinstance(m_info['fields'], dict):
                    for fname, f_info in m_info['fields'].items():
                        if isinstance(f_info, dict):
                            for f_key in ('string', 'help', 'placeholder'):
                                if f_key in f_info and isinstance(f_info[f_key], str):
                                    f_info[f_key] = self.apply_terms_to_text(f_info[f_key], terms)

        return views_result
