# -*- coding: utf-8 -*-
import logging
import re
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Modules whose models / actions / menus / JS strings form "Manufacturing".
KITCHEN_EXTRA_MODULES = ('hudson_shopfloor',)


# Default label set (same as data/kitchen_label_data.xml), used to seed a
# company's own labels when Kitchen Mode is enabled for it.
DEFAULT_KITCHEN_LABELS = [
    {'name': 'Bills of Materials', 'kitchen_label': 'Recipes', 'sequence': 10},
    {'name': 'Manufacturing Orders', 'kitchen_label': 'Production Orders', 'sequence': 20},
    {'name': 'Work Orders', 'kitchen_label': 'Kitchen Tasks', 'sequence': 30},
    {'name': 'Work Centers', 'kitchen_label': 'Kitchen Stations', 'sequence': 40},
    {'name': 'Components', 'kitchen_label': 'Ingredients', 'sequence': 50},
    {'name': 'Operations', 'kitchen_label': 'Prep Steps', 'sequence': 60},
    {'name': 'Scrap Orders', 'kitchen_label': 'Wastage', 'sequence': 70},
    {'name': 'Unbuild Orders', 'kitchen_label': 'Batch Reversals', 'sequence': 80},
    {'name': 'Productivity Losses', 'kitchen_label': 'Downtime Reasons', 'sequence': 90},
    {'name': 'Planning by Work Center', 'kitchen_label': 'Station Planning', 'sequence': 100},
    {'name': 'Overall Equipment Effectiveness', 'kitchen_label': 'Station Efficiency', 'sequence': 110},
    {'name': 'Shop Floor', 'kitchen_label': 'Kitchen Floor', 'sequence': 120},
]


def is_kitchen_terms_module(module_name):
    """True if the technical module name belongs to Manufacturing."""
    if not module_name:
        return False
    return module_name == 'mrp' or module_name.startswith('mrp_') or module_name in KITCHEN_EXTRA_MODULES


def is_kitchen_terms_xmlid(xml_id):
    return bool(xml_id) and '.' in xml_id and is_kitchen_terms_module(xml_id.split('.', 1)[0])


def is_kitchen_terms_model(model):
    """
    True if the model was *created* by a Manufacturing module.

    ``_original_module`` is the module that defined the model. ``_module`` must
    not be used: it is the last module that *extended* the model, so shared
    models such as res.config.settings or res.company would be wrongly treated
    as Manufacturing models (which is how labels leaked into Payroll/Settings).
    """
    if model is None or model._name == 'kitchen.label':
        return False
    return is_kitchen_terms_module(getattr(model, '_original_module', None))


def _is_plural(word):
    if not word:
        return False
    w = word.strip().split()[-1].lower()
    if w in ('wastage', 'scrap', 'production', 'planning', 'efficiency', 'floor', 'loss'):
        return False
    return w.endswith('s') and not w.endswith('ss')


def _to_singular(phrase):
    if not phrase:
        return phrase
    parts = phrase.strip().split()
    if not parts:
        return phrase
    last = parts[-1]
    if last.lower() in ('wastage', 'scrap', 'reversal', 'production', 'planning', 'efficiency', 'floor'):
        return phrase
    if last.lower().endswith('ies') and len(last) > 3:
        singular_last = last[:-3] + 'y'
    elif last.lower().endswith('es') and len(last) > 3 and last.lower()[-3] in ('s', 'x', 'z', 'c', 'h'):
        singular_last = last[:-2]
    elif last.lower().endswith('s') and not last.lower().endswith('ss') and len(last) > 2:
        singular_last = last[:-1]
    else:
        singular_last = last
    return " ".join(parts[:-1] + [singular_last])


def _to_plural(phrase):
    if not phrase:
        return phrase
    parts = phrase.strip().split()
    if not parts:
        return phrase
    last = parts[-1]
    if last.lower() in ('wastage', 'scrap', 'planning', 'efficiency', 'floor'):
        return phrase
    if _is_plural(phrase):
        return phrase
    if last.lower().endswith('y') and len(last) > 1 and last.lower()[-2] not in 'aeiou':
        plural_last = last[:-1] + 'ies'
    elif last.lower().endswith(('s', 'x', 'z', 'ch', 'sh')):
        plural_last = last + 'es'
    else:
        plural_last = last + 's'
    return " ".join(parts[:-1] + [plural_last])


class KitchenLabel(models.Model):
    _name = 'kitchen.label'
    _description = 'Kitchen Mode Terminology Mapping'
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(
        string="Standard Label",
        required=True,
        index=True,
        help="The standard Manufacturing terminology to be replaced (e.g., Bills of Materials)."
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
    notes = fields.Text(
        string="Notes",
        help="Optional notes or context about this terminology mapping."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self._get_kitchen_company(),
        index=True,
        help="Leave blank to make this mapping available to all companies (global), or select a specific company to restrict it."
    )

    @api.constrains('name', 'company_id')
    def _check_unique_name(self):
        for record in self:
            if not record.name:
                continue
            domain = [
                ('id', '!=', record.id),
                ('name', '=ilike', record.name.strip()),
                ('company_id', '=', record.company_id.id if record.company_id else False),
            ]
            duplicate = self.sudo().with_context(active_test=False).search(domain, limit=1)
            if duplicate:
                comp_desc = f" for company '{record.company_id.name}'" if record.company_id else " across all companies (global)"
                raise ValidationError(
                    f"A terminology mapping for '{record.name}' already exists{comp_desc}. "
                    "Please edit the existing mapping instead of creating a duplicate."
                )

    _LEGACY_XMLIDS = (
        'label_manufacturing_order', 'label_manufacturings', 'label_manufacturing',
        'label_bill_of_materials','label_bill_of_material', 'label_boms', 'label_bom',
        'label_work_order', 'label_work_center', 'label_component', 'label_operation',
        'label_scrap_order', 'label_scrap', 'label_unbuild_order', 'label_unbuild',
        'label_productivity_loss',
        'label_quality_checks', 'label_quality_check', 'label_quality_points', 'label_quality_point',
        'label_quality_alerts', 'label_quality_alert',
        'label_maintenance_requests', 'label_maintenance_request',
        'label_maintenance_teams', 'label_maintenance_team',
        'label_engineering_change_orders', 'label_engineering_change_order',
        'label_ecos', 'label_eco',
    )

    def init(self):
        super().init()
        # Remove legacy seeded records if any
        self.env.cr.execute("""
            WITH legacy AS (
                DELETE FROM ir_model_data
                 WHERE module = 'hudson_kitchen_terms'
                   AND model = 'kitchen.label'
                   AND name = ANY(%s)
             RETURNING res_id
            )
            DELETE FROM kitchen_label WHERE id IN (SELECT res_id FROM legacy)
        """, [list(self._LEGACY_XMLIDS)])
        # Companies that already use Kitchen Mode get their own label set
        if 'kitchen_mode' in self.env['res.company']._fields:
            self.env.cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'res_company' AND column_name = 'kitchen_mode'")
            if self.env.cr.fetchone():
                companies = self.env['res.company'].sudo().search([('kitchen_mode', '=', True)])
                if companies:
                    self._ensure_company_labels(companies)

    @api.model
    def _ensure_company_labels(self, companies):
        """
        Give each company its own full set of labels the first time Kitchen
        Mode is used, so editing one company's labels never changes another
        company. The set is copied from the global (company-less) labels when
        they exist, otherwise from DEFAULT_KITCHEN_LABELS.
        """
        Label = self.sudo().with_context(active_test=False)
        globals_ = Label.search([('company_id', '=', False)], order='sequence, id')
        template = [
            {'name': g.name, 'kitchen_label': g.kitchen_label, 'sequence': g.sequence,
             'active': g.active, 'notes': g.notes}
            for g in globals_
        ] or [dict(vals) for vals in DEFAULT_KITCHEN_LABELS]
        for company in companies:
            existing = {n.strip().lower() for n in Label.search([('company_id', '=', company.id)]).mapped('name') if n}
            to_create = [
                dict(vals, company_id=company.id)
                for vals in template
                if vals['name'].strip().lower() not in existing
            ]
            if to_create:
                Label.create(to_create)
                _logger.info("Kitchen labels created for company %s (%s)", company.name, company.id)

    @api.model
    def _invalidate_terminology_caches(self):
        """
        Terminology is applied on top of the cached menus/views, so this only
        drops the 'default' ormcache (menus) so every worker reloads cleanly.
        """
        self.env.transaction.invalidate_ormcache('default')

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
    def _get_variants_for_record(self, std_name, kitch_val):
        """
        Derives all singular, plural, and abbreviation variants for a single record.
        This removes the need for duplicate records in the database.
        """
        std = (std_name or '').strip()
        kitch = (kitch_val or '').strip()
        if not std or not kitch:
            return {}
        std_lower = std.lower()

        if _is_plural(std):
            kitch_plural = kitch
            kitch_singular = _to_singular(kitch)
        else:
            kitch_singular = kitch
            kitch_plural = _to_plural(kitch)

        res = {}
        if std_lower in ("bills of materials", "bill of materials", "bill of material", "boms", "bom") or ("bill" in std_lower and "material" in std_lower):
            res["Bills of Materials"] = kitch_plural
            res["Bill of Materials"] = kitch_singular
            res["Bill of Material"] = kitch_singular
            res["BoMs"] = kitch_plural
            res["BoM"] = kitch_singular
        elif std_lower in ("manufacturing orders", "manufacturing order", "manufacturings", "manufacturing"):
            res["Manufacturing Orders"] = kitch_plural
            res["Manufacturing Order"] = kitch_singular
            res["Manufacturings"] = kitch_plural
            if kitch_plural.lower().endswith("orders"):
                root = kitch_plural[:-6].strip()
                res["Manufacturing"] = f"{root} Production" if "kitchen" in root.lower() else (root if root.lower().endswith("production") else f"{root} Production")
            else:
                res["Manufacturing"] = kitch or "Kitchen Production"
        elif std_lower in ("work orders", "work order"):
            res["Work Orders"] = kitch_plural
            res["Work Order"] = kitch_singular
        elif "planning" in std_lower and "work center" in std_lower:
            res["Planning by Work Center"] = kitch
        elif std_lower in ("work centers", "work center"):
            res["Work Centers"] = kitch_plural
            res["Work Center"] = kitch_singular
        elif std_lower in ("components", "component"):
            res["Components"] = kitch_plural
            res["Component"] = kitch_singular
        elif std_lower in ("operations", "operation"):
            res["Operations"] = kitch_plural
            res["Operation"] = kitch_singular
        elif std_lower in ("scrap orders", "scrap order", "scrap"):
            res["Scrap Orders"] = kitch_plural if kitch_plural.lower() != 'wastage' else kitch
            res["Scrap Order"] = kitch_singular
            res["Scrap"] = kitch_singular
        elif std_lower in ("unbuild orders", "unbuild order", "unbuild"):
            res["Unbuild Orders"] = kitch_plural
            res["Unbuild Order"] = kitch_singular
            res["Unbuild"] = kitch_singular
        elif std_lower in ("productivity losses", "productivity loss"):
            res["Productivity Losses"] = kitch_plural
            res["Productivity Loss"] = kitch_singular
        elif "overall equipment effectiveness" in std_lower or std_lower == "oee":
            res["Overall Equipment Effectiveness"] = kitch
            res["OEE"] = kitch
        elif std_lower == "shop floor":
            res["Shop Floor"] = kitch
        else:
            res[std] = kitch
            if _is_plural(std):
                res[_to_singular(std)] = kitch_singular
            else:
                res[_to_plural(std)] = kitch_plural
        return res

    @api.model
    def _get_kitchen_company(self):
        """
        The company whose Kitchen Mode / labels apply to the current request.

        In multi-company environments:
        - Plain HTTP requests (page load, load_menus, session_info) read from
          the active company id in the 'cids' cookie.
        - JSON-RPC requests carry allowed_company_ids in context.
        """
        try:
            from odoo.http import request
            if request:
                if request.context and request.context.get('allowed_company_ids'):
                    cid = request.context['allowed_company_ids'][0]
                    if cid and cid in self.env.user.company_ids.ids:
                        return self.env['res.company'].browse(cid)
                cids = request.cookies.get('cids')
                if cids:
                    try:
                        cid = int(str(cids).replace(',', '-').split('-')[0])
                    except ValueError:
                        cid = None
                    if cid and cid in self.env.user.company_ids.ids:
                        return self.env['res.company'].browse(cid)
        except Exception:
            pass

        if self.env.context.get('allowed_company_ids'):
            cid = self.env.context['allowed_company_ids'][0]
            if cid and cid in self.env.user.company_ids.ids:
                return self.env['res.company'].browse(cid)

        return self.env.company

    @api.model
    def get_terms_mapping(self, company=None):
        """
        Returns active terms mapping as a list of tuples:
        [(standard_label, kitchen_label), ...]
        Sorted by length of standard_label descending so compound phrases
        are replaced before shorter substrings.

        Supports Multi-Company:
        - If the company does not have kitchen_mode enabled, returns empty list [].
        - Starts from DEFAULT_KITCHEN_LABELS.
        - Global records override defaults.
        - Company-specific records override global records.
        """
        target_company = company or self._get_kitchen_company()
        if target_company and not target_company.kitchen_mode:
            return []

        company_id = target_company.id if target_company else False

        # 1. Base default mappings
        mapping_dict = {}
        for item in DEFAULT_KITCHEN_LABELS:
            mapping_dict.update(self._get_variants_for_record(item['name'], item['kitchen_label']))

        # 2. Database records
        domain = [('company_id', 'in', [False, company_id] if company_id else [False])]
        records = self.sudo().with_context(active_test=False).search(domain, order='sequence, id')

        global_records = records.filtered(lambda r: not r.company_id)
        company_records = records.filtered(lambda r: r.company_id.id == company_id) if company_id else self.browse()

        # If target_company has kitchen_mode enabled but no records in DB yet, auto-seed them
        if target_company and target_company.kitchen_mode and not company_records:
            try:
                self._ensure_company_labels(target_company)
                company_records = self.sudo().with_context(active_test=False).search([('company_id', '=', company_id)], order='sequence, id')
            except Exception as e:
                _logger.warning("Could not auto-seed company labels: %s", e)

        # Apply global records (override defaults)
        for r in global_records:
            if not r.name:
                continue
            variants = self._get_variants_for_record(r.name, r.kitchen_label or '')
            for std, kitch in variants.items():
                if not r.active:
                    mapping_dict.pop(std, None)
                else:
                    mapping_dict[std] = kitch

        # Apply company-specific records (override global & defaults)
        for r in company_records:
            if not r.name:
                continue
            variants = self._get_variants_for_record(r.name, r.kitchen_label or '')
            for std, kitch in variants.items():
                if not r.active:
                    mapping_dict.pop(std, None)
                else:
                    mapping_dict[std] = kitch

        terms = [(k, v) for k, v in mapping_dict.items() if v]
        # Sort by length descending to ensure longer phrases match first
        terms.sort(key=lambda item: len(item[0]), reverse=True)
        return terms

    @api.model
    def get_terms_dict(self, company=None):
        """
        Returns active terms as a dict: {standard_label: kitchen_label, ...}
        for use in the web client frontend session.
        """
        mapping = self.get_terms_mapping(company=company)
        return {std: kitch for std, kitch in mapping}

    @api.model
    def apply_terms_to_text(self, text, terms=None, company=None):
        """
        Replaces standard terms with kitchen terms in text while preserving casing.
        """
        if not text or not isinstance(text, str):
            return text
        if terms is None:
            terms = self.get_terms_mapping(company=company)
        if not terms:
            return text

        for old_term, new_term in terms:
            left = r'\b' if old_term[0].isalnum() else r'(?:\A|\s)'
            right = r'\b' if old_term[-1].isalnum() else r'(?:\Z|\s)'
            pattern = re.compile(left + re.escape(old_term) + right, re.IGNORECASE)

            def repl(match, new_term=new_term):
                matched = match.group(0)
                # Keep surrounding whitespace captured by non-word boundaries.
                lead = matched[:len(matched) - len(matched.lstrip())]
                trail = matched[len(matched.rstrip()):]
                core = matched.strip()
                if core.isupper() and len(core) > 1 and not new_term.isupper():
                    out = new_term.upper()
                elif core.islower():
                    out = new_term.lower()
                else:
                    # Keep the label exactly as the user typed it.
                    out = new_term
                return lead + out + trail

            text = pattern.sub(repl, text)
        return text

    @api.model
    def apply_terms_to_arch(self, arch_str, terms=None, company=None):
        """
        Parses XML arch and transforms visible presentation attributes
        (string, title, placeholder, help, confirm, sum, avg) and text content
        without touching any technical attributes (name, model, domain, context, etc.).
        """
        if not arch_str or not isinstance(arch_str, str):
            return arch_str
        if terms is None:
            terms = self.get_terms_mapping(company=company)
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
    def apply_terms_to_menus(self, menus_dict, terms=None, company=None):
        """
        Transforms visible menu titles in menus_dict returned by ir.ui.menu.load_menus().
        Strictly restricted to Manufacturing (mrp) menus. Menus belonging to other
        modules (Payroll, HR, Accounting, etc.) are never modified.
        """
        if not menus_dict or not isinstance(menus_dict, dict):
            return menus_dict
        if terms is None:
            terms = self.get_terms_mapping(company=company)
        if not terms:
            return menus_dict

        mrp_root = self.env.ref('mrp.menu_mrp_root', raise_if_not_found=False)
        if not mrp_root:
            return menus_dict
        kitchen_menu = self.env.ref('hudson_kitchen_terms.menu_kitchen_label', raise_if_not_found=False)

        # The result of load_menus() is shared through ormcache: never mutate
        # it in place, only replace the entries that change.
        menus_copy = dict(menus_dict)
        for menu_id, menu in menus_dict.items():
            if not isinstance(menu, dict) or menu.get('app_id') != mrp_root.id:
                continue
            if kitchen_menu and menu.get('id') == kitchen_menu.id:
                continue
            name = menu.get('name')
            if isinstance(name, str):
                new_name = self.apply_terms_to_text(name, terms)
                if new_name != name:
                    menus_copy[menu_id] = dict(menu, name=new_name)
        return menus_copy

    @api.model
    def apply_terms_to_action_dict(self, action_dict, terms=None, company=None):
        """
        Transforms action names, display_names, and help in action dicts
        returned to the web client for Manufacturing actions.
        """
        if not action_dict or not isinstance(action_dict, dict):
            return action_dict
        if terms is None:
            terms = self.get_terms_mapping(company=company)
        if not terms:
            return action_dict

        res = dict(action_dict)
        for key in ('name', 'display_name', 'help'):
            if key in res and isinstance(res[key], str):
                res[key] = self.apply_terms_to_text(res[key], terms)
        return res

    @api.model
    def apply_terms_to_views_result(self, views_result, terms=None, company=None):
        """
        Transforms views architecture and model fields descriptions in
        the result returned by Base.get_views() for Manufacturing models.
        """
        if not views_result or not isinstance(views_result, dict):
            return views_result
        if terms is None:
            terms = self.get_terms_mapping(company=company)
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
