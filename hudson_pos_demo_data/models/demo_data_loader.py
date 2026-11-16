# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import base64
import hashlib
import logging
import os
from odoo.tools import convert_file
from odoo import Command

_logger = logging.getLogger(__name__)

DEMO_XML_FILES = [
    'demo/pos_categories.xml',
    'demo/product_tags.xml',
    'demo/courses.xml',
    'demo/note_models.xml',
    'demo/floors_and_tables.xml',
    'demo/pricelists.xml',
    'demo/loyalty_programs.xml',
    'demo/products_resto.xml',
    'demo/recruitment_demo.xml',
]

IMAGE_SEARCH_PATHS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'src', 'img')),
    r'C:\Program Files\Odoo 20.0.20260928\server\odoo\addons\pos_restaurant\static\img',
    r'C:\Program Files\Odoo 20.0.20260928\server\odoo\addons\point_of_sale\static\img',
]

PRODUCT_IMAGE_MAP = {
    'Bacon Burger': 'th-burger.png',
    'Cheese Burger': 'th-cheeseburger.png',
    'Burger Menu Combo': 'combo-hamb.png',
    'Club Sandwich': 'th-club.png',
    'Mozzarella Sandwich': 'th-mozza.png',
    'Chicken Curry Sandwich': 'th-sandwich.png',
    'Spicy Tuna Sandwich': 'th-tuna.png',
    'Pizza Margherita': 'th-pizza-ma.png',
    'Pizza Vegetarian': 'th-pizza-ve.png',
    'Funghi': 'th-pizza-fu.png',
    'Pasta 4 Formaggi': 'th-pasta-4f.png',
    'Pasta Bolognese': 'th-pasta.png',
    'Pasta Lunch Combo': 'th-pasta.png',
    'Lunch Maki 18pc': 'th-maki.png',
    'Lunch Salmon 20pc': 'th-salmon.png',
    'Lunch Temaki mix 3pc': 'th-temaki.png',
    'Salmon and Avocado': 'th-salmon-avocado.png',
    'Sushi Lunch Combo': 'sushi-combo.png',
    'Coca-Cola': 'th-coke.png',
    'Fanta': 'th-fanta.png',
    'Water': 'th-water.png',
    'Schweppes': 'th-schweppes.png',
    'Minute Maid': 'th-minute_maid.png',
    'Milkshake Banana': 'th-milkshake_banana.png',
    'Espresso': 'th-espresso.png',
    'Green Tea': 'th-green_tea.png',
    'Ice Tea': 'th-ice_tea.png',
    'Signature Hot Chocolate': 'product_hot_chocolate.png',
    'Warm Apple Pie': 'product_apple_pie.png',
    'Artisan Chocolate Croissant': 'product_pain_au_chocolat.png',
    'Double Chocolate Chip Cookie': 'product_chocolate_chip_cookie.png',
    'New York Cheesecake': 'product_new_york_cheesecake.png',
    'Chocolate Lava Cake': 'product_chocolate_lava_cake.png',
    'Crème Brûlée': 'product_creme_brulee.png',
    'Tiramisu': 'product_tiramisu.png',
    'Fresh Strawberry Tart': 'product_cherry_pie.png',
    'Vanilla Bean Ice Cream Sundae': 'product_ice_cream_sundae.png',
    'French Macarons Box (6 pcs)': 'product_french_macarons.png',
    'Belgian Milk Chocolate Truffles': 'product_belgian_truffles.png',
    'Dark Chocolate Bar 70%': 'product_dark_chocolate_bar.png',
    'White Chocolate Raspberry Bar': 'product_white_chocolate_bar.png',
    'Luxury Chocolate Gift Box': 'product_luxury_chocolate_box.png',
    'Dessert & Hot Drink Combo': 'product_dessert_combo.png',
    'Fudge Brownie & Ice Cream': 'product_fudge_brownie.png',
}

LEGACY_PLACEHOLDER_IMAGES = (
    'pastries-icon.png',
    'soft-drink-icon.png',
)

LEGACY_REUSED_IMAGES = {
    'Double Chocolate Chip Cookie': 'product_blueberry_muffin.png',
    'Vanilla Bean Ice Cream Sundae': 'th-milkshake_banana.png',
    'New York Cheesecake': 'product_pecan_pie.png',
}


def load_pos_demo_data(env, pos_config_ids=None):
    """
    Complete Restaurant & Cafe POS Demo Data Loader:
    - Purges duplicate/orphan floor plans.
    - Loads categories, tags, courses, prep notes, floors, pricelists, loyalty, and products.
    - Creates real POS Combo Choices and configures combo products with type='combo'.
    - Configures 2 distinct food & beverage POS configs: Restaurant (Dine-in) & Cafe (Register).
    - Sets beautiful graphical floor plan table positions.
    - Attaches high-res product images and initial warehouse stock.
    """
    _logger.info("Hudson POS: Starting Restaurant & Cafe Demo Data loader...")

    # 1. Clean up duplicate / orphan floors created previously
    with env.cr.savepoint():
        _cleanup_duplicate_floors(env)

    # 2. Pre-bind existing records to ir.model.data
    with env.cr.savepoint():
        _pre_bind_existing_records(env)

    # 3. Execute all standard XML demo files safely inside savepoints
    for xml_file in DEMO_XML_FILES:
        if xml_file == 'demo/recruitment_demo.xml' and (
            'hr.job' not in env or 'is_published' not in env['hr.job']._fields
        ):
            _logger.info("Skipping %s because website_hr_recruitment is not installed.", xml_file)
            continue
        try:
            with env.cr.savepoint():
                _logger.info("Loading demo XML: %s", xml_file)
                convert_file(
                    env,
                    'hudson_pos_demo_data',
                    xml_file,
                    idref={},
                    mode='init',
                    noupdate=True,
                )
        except Exception as e:
            _logger.error("Failed to load demo file %s: %s", xml_file, e)

    # 4. Clean up any 'My Company' duplicate floor created by Odoo during POS init
    with env.cr.savepoint():
        _cleanup_duplicate_floors(env)

    # 5. Configure graphical floor layouts and table positions
    try:
        with env.cr.savepoint():
            _configure_floors_and_tables(env)
    except Exception as e:
        _logger.warning("Could not configure floors and tables: %s", e)

    # 6. Ensure Restaurant and Cafe POS configurations exist
    try:
        with env.cr.savepoint():
            _ensure_default_shops(env)
    except Exception as e:
        _logger.warning("Could not ensure default POS shops: %s", e)

    # 7. Configure true POS Combos (product.combo & type='combo')
    try:
        with env.cr.savepoint():
            _configure_combos(env)
    except Exception as e:
        _logger.warning("Could not configure POS combos: %s", e)

    # 8. Attach images to products
    try:
        with env.cr.savepoint():
            _load_product_images(env)
    except Exception as e:
        _logger.warning("Could not load product images: %s", e)

    # 8b. Configure advanced loyalty programs, product rules/rewards, and sample cards
    try:
        with env.cr.savepoint():
            _configure_loyalty_demo_data(env)
    except Exception as e:
        _logger.warning("Could not configure loyalty demo data: %s", e)

    # 9. Link floors, screens, pricelists, and loyalty programs to POS configs
    try:
        with env.cr.savepoint():
            _post_process_pos_configs(env, pos_config_ids)
    except Exception as e:
        _logger.warning("Could not post-process POS configs: %s", e)

    # Remove any dummy company floor auto-created by pos_restaurant during shop creation
    with env.cr.savepoint():
        _cleanup_duplicate_floors(env)

    # 10. Initialize stock inventory
    try:
        with env.cr.savepoint():
            _load_stock_inventory(env)
    except Exception as e:
        _logger.warning("Could not load stock inventory: %s", e)

    # 11. Configure & publish recruitment job openings & sample applicants
    try:
        with env.cr.savepoint():
            _load_recruitment_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load recruitment demo data: %s", e)

    # 12. Load Resto Cafe Solutions eLearning demo data (courses, quizzes, certification, paid course)
    try:
        from .demo_elearning_suite import load_elearning_suite_demo_data
        load_elearning_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load eLearning demo data: %s", e)

    # 13. Create sample POS orders for demonstration
    try:
        with env.cr.savepoint():
            _load_sample_pos_orders(env)
    except Exception as e:
        _logger.warning("Could not load sample POS orders: %s", e)

    # 14. Create full connected HR Suite demo data (Employees, Attendance, Time Off, Fleet, Lunch, Expenses, Payroll)
    try:
        with env.cr.savepoint():
            from .demo_hr_suite import load_hr_suite_demo_data
            load_hr_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load HR suite demo data: %s", e)

    # 15. Create full connected Business Suite demo data (CRM, Sales, Inventory, Purchase, MRP, Maintenance, Events, Survey)
    try:
        with env.cr.savepoint():
            from .demo_business_suite import load_business_suite_demo_data
            load_business_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Business suite demo data: %s", e)

    # 16. Create Restaurant & Cafe Inventory Suite demo data (Ingredients, Packaging, Vendors, Locations, Rules, BoMs, Moves)
    try:
        with env.cr.savepoint():
            from .demo_inventory_suite import load_inventory_suite_demo_data
            load_inventory_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Inventory suite demo data: %s", e)

    # 17. Load Resto Cafe Solutions CRM demo data (Leads, Pipeline, Teams, Activities, Lost reasons, UTM)
    try:
        from .demo_crm_suite import load_crm_suite_demo_data
        load_crm_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load CRM suite demo data: %s", e)

    # 18. Load Resto Cafe Solutions Blog, Events and Email Marketing demo data (installed apps only)
    try:
        from .demo_marketing_suite import load_marketing_suite_demo_data
        load_marketing_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Marketing suite demo data: %s", e)

    # 19. Load Resto Cafe Solutions packaged-food webshop (eCommerce) demo data
    try:
        from .demo_ecommerce_suite import load_ecommerce_suite_demo_data
        load_ecommerce_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load eCommerce suite demo data: %s", e)

    # 20. Load Resto Cafe Solutions Sales demo data (catering quotations, templates, headers/footers, promotions)
    try:
        from .demo_sales_suite import load_sales_suite_demo_data
        load_sales_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Sales suite demo data: %s", e)

    # 21. Load Resto Cafe Solutions Purchase & Inventory demo data
    try:
        from .demo_purchase_suite import load_purchase_suite_demo_data
        load_purchase_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Purchase & Inventory demo data: %s", e)

    # 22. Load Resto Cafe Solutions Manufacturing & Shop Floor demo data
    try:
        from .demo_mrp_suite import load_mrp_suite_demo_data
        load_mrp_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Manufacturing & Shop Floor demo data: %s", e)

    # 23. Load Resto Cafe Solutions Quality & Maintenance demo data
    try:
        from .demo_quality_maintenance_suite import load_quality_maintenance_suite_demo_data
        load_quality_maintenance_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Quality & Maintenance demo data: %s", e)

    # 23b. Load Resto Cafe Solutions Inventory features demo data (expiry lots, locations, packages, UoM,
    #      removal strategies, reordering rules, multi-step routes, receipt quality checks, returns)
    try:
        from .demo_inventory_features_suite import load_inventory_features_suite_demo_data
        load_inventory_features_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Inventory features demo data: %s", e)

    # 24. Load Resto Cafe Solutions Rental & Subscriptions demo data
    try:
        from .demo_rental_subscription_suite import load_rental_subscription_suite_demo_data
        load_rental_subscription_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Rental & Subscriptions demo data: %s", e)

    # 25. Load Resto Cafe Solutions Planning demo data
    try:
        from .demo_planning_suite import load_planning_suite_demo_data
        load_planning_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Planning demo data: %s", e)

    # 26. Load Resto Cafe Solutions Project & Timesheet demo data
    try:
        from .demo_project_suite import load_project_suite_demo_data
        load_project_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Project & Timesheet demo data: %s", e)

    # 27. Load Resto Cafe Solutions Fleet, Lunch & Expenses demo data
    try:
        from .demo_fleet_lunch_expense_suite import load_fleet_lunch_expense_suite_demo_data
        load_fleet_lunch_expense_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Fleet, Lunch & Expenses demo data: %s", e)

    # 28. Load Resto Cafe Solutions Approvals & PLM demo data
    try:
        from .demo_approvals_plm_suite import load_approvals_plm_suite_demo_data
        load_approvals_plm_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Approvals & PLM demo data: %s", e)

    # 29. Load Resto Cafe Solutions Helpdesk demo data
    try:
        from .demo_helpdesk_suite import load_helpdesk_suite_demo_data
        load_helpdesk_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Helpdesk demo data: %s", e)

    # 30. Load Resto Cafe Solutions HR people demo data
    try:
        from .demo_hr_people_suite import load_hr_people_suite_demo_data
        load_hr_people_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load HR people demo data: %s", e)

    # 31. Load Resto Cafe Solutions Recruitment & Payroll demo data
    try:
        from .demo_recruitment_payroll_suite import load_recruitment_payroll_suite_demo_data
        load_recruitment_payroll_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Recruitment & Payroll demo data: %s", e)

    # 32. Load Resto Cafe Solutions Collaboration demo data
    try:
        from .demo_collaboration_suite import load_collaboration_suite_demo_data
        load_collaboration_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Collaboration demo data: %s", e)

    # 33. Load Resto Cafe Solutions Company setup demo data
    try:
        from .demo_company_setup_suite import load_company_setup_suite_demo_data
        load_company_setup_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Company setup demo data: %s", e)

    # 34. Field Service jobs linked to Project tasks, Timesheets and Planning shifts
    try:
        from .demo_field_service_suite import load_field_service_suite_demo_data
        load_field_service_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Field Service demo data: %s", e)

    _logger.info("Hudson POS: Restaurant & Cafe demo data loaded successfully.")
    return True


def _cleanup_duplicate_floors(env):
    """
    Removes auto-generated dummy floors named after the company ('My Company') when orphaned without POS configs.
    """
    RestaurantFloor = env['restaurant.floor'].sudo()
    dummy_names = list({n for n in ['My Company', env.company.name] if n})
    dummy_floors = RestaurantFloor.search([
        ('name', 'in', dummy_names),
        ('pos_config_ids', '=', False),
    ])
    for flr in dummy_floors:
        try:
            with env.cr.savepoint():
                flr.table_ids.unlink()
                flr.unlink()
        except Exception as e:
            _logger.warning("Could not unlink dummy floor %s: %s", flr.id, e)


def _configure_floors_and_tables(env):
    """
    Configures visual background and grid coordinates for Main Floor and Patio tables.
    """
    RestaurantFloor = env['restaurant.floor'].sudo()
    main_floor = RestaurantFloor.search([('name', '=', 'Main Floor')], limit=1)
    patio = RestaurantFloor.search([('name', '=', 'Patio')], limit=1)

    if main_floor:
        try:
            main_floor.write({'floor_plan_layout': {'bgColor': 'texture-wood-v'}})
            for idx, tbl in enumerate(main_floor.table_ids.sorted('table_number')):
                row = idx // 4
                col = idx % 4
                shape = 'round' if tbl.seats == 2 else 'square'
                color = 'blue' if tbl.seats >= 6 else 'green'
                tbl.write({
                    'floor_plan_layout': {
                        'top': 80 + row * 160,
                        'left': 80 + col * 170,
                        'width': 100,
                        'height': 100,
                        'shape': shape,
                        'color': color,
                    }
                })
        except Exception as e:
            _logger.warning("Could not set floor layout for Main Floor: %s", e)

    if patio:
        try:
            patio.write({'floor_plan_layout': {'bgColor': 'texture-stone-v'}})
            for idx, tbl in enumerate(patio.table_ids.sorted('table_number')):
                row = idx // 4
                col = idx % 4
                shape = 'round' if tbl.seats == 2 else 'square'
                tbl.write({
                    'floor_plan_layout': {
                        'top': 80 + row * 160,
                        'left': 80 + col * 170,
                        'width': 100,
                        'height': 100,
                        'shape': shape,
                        'color': 'orange',
                    }
                })
        except Exception as e:
            _logger.warning("Could not set floor layout for Patio: %s", e)


def _ensure_default_shops(env):
    """
    Ensures 2 distinct food & beverage POS shops exist:
    1. Restaurant (Dine-in with Tables, Floors, Courses, Prep notes)
    2. Cafe (Counter-service Register with Drinks, Coffee, Desserts, Combos)
    """
    PosConfig = env['pos.config'].sudo()
    RestaurantFloor = env['restaurant.floor'].sudo()

    floors = RestaurantFloor.search([('name', 'in', ['Main Floor', 'Patio'])])

    # 1. Restaurant POS
    resto = PosConfig.search([('name', '=', 'Restaurant')], limit=1)
    if not resto:
        resto = PosConfig.search([('module_pos_restaurant', '=', True)], limit=1)
    if not resto:
        resto = PosConfig.create({
            'name': 'Restaurant',
            'module_pos_restaurant': True,
        })
    else:
        resto.write({
            'name': 'Restaurant',
            'module_pos_restaurant': True,
        })

    if not resto.current_session_id:
        resto_vals = {}
        if hasattr(resto, 'default_screen'):
            resto_vals['default_screen'] = 'tables'
        if hasattr(resto, 'use_course_allocation'):
            resto_vals['use_course_allocation'] = True
        if floors:
            resto_vals['floor_ids'] = [Command.set(floors.ids)]
        resto.write(resto_vals)

    # 2. Cafe POS (Counter service / Quick register)
    cafe = PosConfig.search([('name', '=', 'Cafe')], limit=1)
    if not cafe:
        cafe = PosConfig.create({
            'name': 'Cafe',
            'module_pos_restaurant': False,
        })
    else:
        cafe.write({
            'module_pos_restaurant': False,
        })

    if not cafe.current_session_id and hasattr(cafe, 'default_screen'):
        cafe.write({'default_screen': 'register'})


def _configure_combos(env):
    """
    Creates Odoo 20 product.combo records and configures combo products with type='combo'.
    """
    if 'product.combo' not in env:
        return

    ProductCombo = env['product.combo'].sudo()
    ProductProduct = env['product.product'].sudo()
    ProductTemplate = env['product.template'].sudo()

    def get_or_create_combo(combo_name, product_names):
        combo = ProductCombo.search([('name', '=', combo_name)], limit=1)
        items = []
        for pname in product_names:
            prod = ProductProduct.search([('name', '=', pname)], limit=1)
            if prod:
                items.append(Command.create({'product_id': prod.id, 'extra_price': 0}))
        if combo:
            combo.combo_item_ids.unlink()
            combo.write({'combo_item_ids': items})
        else:
            combo = ProductCombo.create({
                'name': combo_name,
                'combo_item_ids': items
            })
        return combo

    c_burgers = get_or_create_combo('Burgers', ['Cheese Burger', 'Bacon Burger'])
    c_drinks = get_or_create_combo('Drinks', ['Coca-Cola', 'Fanta', 'Minute Maid', 'Water', 'Milkshake Banana'])
    c_sushi = get_or_create_combo('Sushi Choices', ['Lunch Maki 18pc', 'Lunch Salmon 20pc', 'Lunch Temaki mix 3pc'])
    c_pasta = get_or_create_combo('Pasta Choices', ['Pasta 4 Formaggi', 'Pasta Bolognese'])
    c_desserts = get_or_create_combo('Dessert Choices', [
        'Tiramisu', 'New York Cheesecake', 'Chocolate Lava Cake', 'Double Chocolate Chip Cookie', 'Warm Apple Pie'
    ])

    combos_map = {
        'Burger Menu Combo': [c_burgers, c_drinks],
        'Sushi Lunch Combo': [c_sushi, c_drinks],
        'Pasta Lunch Combo': [c_pasta, c_drinks],
        'Dessert & Hot Drink Combo': [c_desserts, c_drinks],
    }

    for prod_name, combo_list in combos_map.items():
        template = ProductTemplate.search([('name', '=', prod_name)], limit=1)
        if template:
            try:
                template.write({
                    'type': 'combo',
                    'combo_ids': [Command.set([c.id for c in combo_list])],
                    'available_in_pos': True,
                })
            except Exception as e:
                _logger.warning("Could not configure combo product %s: %s", prod_name, e)


def _load_product_images(env, replace_placeholders=False):
    """
    Attaches high-resolution product images to food, drink, and dessert products.
    Replaces missing images and outline placeholder icons, and optionally upgrades
    legacy reused product photos during migrations without overwriting custom images.
    """
    ProductTemplate = env['product.template'].sudo()
    IrAttachment = env['ir.attachment'].sudo()

    def get_image_bytes(filename):
        for base_dir in IMAGE_SEARCH_PATHS:
            full_path = os.path.join(base_dir, filename)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'rb') as f:
                        return f.read()
                except Exception:
                    pass
        return None

    def get_file_sha1(filename):
        data = get_image_bytes(filename)
        return hashlib.sha1(data).hexdigest() if data else None

    placeholder_hashes = {
        h for fname in LEGACY_PLACEHOLDER_IMAGES
        if (h := get_file_sha1(fname))
    }
    placeholder_hashes.update({
        'ed345d90cf7a5246fec80d9656351666e6a3f6a4',  # pastries-icon.png
        'c2232be8ab8840c29a0a144ab7fdd459abe4320f',  # soft-drink-icon.png
    })

    legacy_reused_known_hashes = {
        'Double Chocolate Chip Cookie': '82100d0a73780e6ba3e45712763108b48a61b658',  # product_blueberry_muffin.png
        'Vanilla Bean Ice Cream Sundae': '3bbd34cf004ebeeeacbb9da67c4d9b444d300183',  # th-milkshake_banana.png
        'New York Cheesecake': 'f66573e2f158a333c2871a5b8f18e7940e140a0f',  # product_pecan_pie.png
    }

    for prod_name, img_filename in PRODUCT_IMAGE_MAP.items():
        tmpl = ProductTemplate.search([('name', '=', prod_name)], limit=1)
        if not tmpl:
            continue

        img_bytes = get_image_bytes(img_filename)
        if not img_bytes:
            continue

        target_sha1 = hashlib.sha1(img_bytes).hexdigest()
        should_write = False

        att = IrAttachment.search([
            ('res_model', '=', 'product.template'),
            ('res_id', '=', tmpl.id),
            ('res_field', '=', 'image_1920'),
        ], limit=1)

        current_sha1 = att.checksum if (att and att.checksum) else None
        if not current_sha1 and tmpl.image_1920:
            try:
                current_sha1 = hashlib.sha1(base64.b64decode(tmpl.image_1920)).hexdigest()
            except Exception:
                current_sha1 = None

        if not current_sha1:
            should_write = True
        elif current_sha1 != target_sha1:
            if current_sha1 in placeholder_hashes:
                should_write = True
            elif replace_placeholders and prod_name in LEGACY_REUSED_IMAGES:
                legacy_hashes = {legacy_reused_known_hashes.get(prod_name)}
                legacy_sha1 = get_file_sha1(LEGACY_REUSED_IMAGES[prod_name])
                if legacy_sha1:
                    legacy_hashes.add(legacy_sha1)
                if current_sha1 in legacy_hashes:
                    should_write = True

        if should_write:
            try:
                tmpl.write({'image_1920': base64.b64encode(img_bytes).decode('utf-8')})
            except Exception as e:
                _logger.warning("Could not set image on %s: %s", prod_name, e)


def _pre_bind_existing_records(env):
    """
    Maps existing records to their XML IDs in ir.model.data to ensure
    convert_file performs updates instead of duplicate inserts.
    """
    def bind_xml(model, xml_name, domain):
        if model not in env:
            return
        rec = env[model].sudo().search(domain, limit=1)
        if rec:
            xdata = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('name', '=', xml_name),
            ], limit=1)
            if not xdata:
                env['ir.model.data'].sudo().create({
                    'module': 'hudson_pos_demo_data',
                    'name': xml_name,
                    'model': model,
                    'res_id': rec.id,
                    'noupdate': True,
                })

    categories = [
        ('pos_category_food', 'Food'),
        ('pos_category_drinks', 'Drinks'),
        ('pos_category_desserts', 'Desserts'),
        ('pos_category_chocolates', 'Chocolates & Sweets'),
    ]
    for xname, cname in categories:
        bind_xml('pos.category', xname, [('name', '=', cname)])

    tags = [
        ('tag_chef_special', 'Chef Special'),
        ('tag_best_seller', 'Best Seller'),
        ('tag_vegetarian', 'Vegetarian'),
        ('tag_gluten_free', 'Gluten Free'),
        ('tag_organic', 'Organic'),
        ('tag_new', 'New'),
    ]
    for xname, tname in tags:
        bind_xml('product.tag', xname, [('name', '=', tname)])

    courses = [
        ('course_starter', 'Starter'),
        ('course_main', 'Main Course'),
        ('course_dessert', 'Dessert'),
        ('course_drinks', 'Drinks'),
    ]
    for xname, cname in courses:
        bind_xml('pos.course', xname, [('name', '=', cname)])

    notes = [
        ('note_extra_spicy', 'Extra Spicy 🌶️'),
        ('note_less_sugar', 'Less Sugar 🍯'),
        ('note_no_ice', 'No Ice 🧊'),
        ('note_gluten_free', 'Gluten Free 🌾'),
        ('note_nut_allergy', 'Nut Allergy Warning 🥜'),
        ('note_takeaway', 'Pack for Takeaway 🥡'),
    ]
    for xname, nname in notes:
        bind_xml('pos.note', xname, [('name', '=', nname)])

    floors = [
        ('floor_main', 'Main Floor'),
        ('floor_patio', 'Patio'),
    ]
    for xname, fname in floors:
        bind_xml('restaurant.floor', xname, [('name', '=', fname)])

    programs = [
        ('loyalty_program_gift_card', 'Gift Cards'),
        ('loyalty_program_ewallet', 'eWallet'),
        ('loyalty_program_happy_hour', 'Happy Hour — 15% Off All Orders'),
        ('loyalty_program_welcome_discount', 'Welcome Discount — 10% Off First Order'),
        ('loyalty_program_weekend_special', 'Weekend Special — 20% Off Beverages'),
        ('loyalty_program_points', 'RestoCafe Loyalty Points'),
        ('loyalty_program_family_combo', 'Family Combo — 20% Off Orders Above ₹500'),
        ('loyalty_program_coupons', 'Seasonal Discount Coupons — 15% Off'),
        ('loyalty_program_promo_discount10', 'Discount Code: DISCOUNT10 — 10% Off Order'),
        ('loyalty_program_promo_burger20', 'Discount Code: BURGER20 — 20% Off Burgers'),
        ('loyalty_program_buy_x_get_y_burger', 'Buy 2 Burgers, Get 1 Soft Drink Free'),
        ('loyalty_program_buy_x_get_y_coffee', 'Buy 2 Hot Drinks, Get 1 Cookie Free'),
        ('loyalty_program_next_order_coupons', 'Spend ₹500, Get 15% Off Next Order'),
    ]
    for xname, pname in programs:
        bind_xml('loyalty.program', xname, [('name', '=', pname)])


def _post_process_pos_configs(env, pos_config_ids=None):
    """
    Links loaded demo floors, pricelists, presets, booking, kiosk, tips,
    and category restrictions to POS configs.
    """
    PosConfig = env['pos.config'].sudo()
    configs = PosConfig.browse(pos_config_ids) if pos_config_ids else PosConfig.search([])

    floors = env['restaurant.floor'].sudo().search([('name', 'in', ['Main Floor', 'Patio'])])
    pricelists = env['product.pricelist'].sudo().search([('name', 'in', ['Happy Hour (20% Off)', 'VIP Member (15% Off)'])])
    loyalty_progs = env['loyalty.program'].sudo().search([])
    demo_cats = env['pos.category'].sudo().search([('name', 'in', ['Food', 'Drinks', 'Desserts', 'Chocolates & Sweets'])])

    # Presets (Dine In, Takeout, Delivery)
    presets = env['pos.preset'].sudo().search([]) if 'pos.preset' in env else False

    # Table Booking appointment type
    app_type = env['appointment.type'].sudo().search([('name', '=', 'Table Booking')], limit=1) if 'appointment.type' in env else False

    # Tip Product (reuse core Odoo POS Tips product first to avoid duplicates)
    tip_prod = env.ref('point_of_sale.product_product_tip', raise_if_not_found=False)
    if tip_prod:
        if not tip_prod.active:
            tip_prod.sudo().write({'active': True})
    else:
        tip_prod = env['product.product'].sudo().with_context(active_test=False).search([('name', '=', 'Tips')], limit=1)
        if tip_prod and not tip_prod.active:
            tip_prod.sudo().write({'active': True})
    if not tip_prod and 'product.product' in env:
        try:
            tip_prod = env['product.product'].sudo().create({
                'name': 'Tips',
                'type': 'service',
                'available_in_pos': True,
                'list_price': 0.0,
            })
        except Exception:
            pass

    for config in configs:
        is_restaurant = any(kw in config.name.lower() for kw in ['resto', 'restau', 'bar', 'ousu'])

        vals = {}
        if not config.current_session_id:
            if is_restaurant:
                vals['module_pos_restaurant'] = True
                if hasattr(config, 'default_screen'):
                    vals['default_screen'] = 'tables'
                if floors:
                    vals['floor_ids'] = [Command.set(floors.ids)]
            else:
                vals['module_pos_restaurant'] = False
                if hasattr(config, 'default_screen'):
                    vals['default_screen'] = 'register'

        # Pricelists
        if pricelists:
            valid_pricelists = pricelists.filtered(lambda p: not p.currency_id or p.currency_id == config.currency_id)
            if valid_pricelists:
                group_pricelist = env.ref('product.group_product_pricelist', raise_if_not_found=False)
                group_user = env.ref('base.group_user', raise_if_not_found=False)
                if group_pricelist and group_user and group_pricelist not in group_user.sudo().all_implied_ids:
                    group_user.sudo()._apply_group(group_pricelist)
                env['res.company'].sudo()._activate_or_create_pricelists()

                vals['use_pricelist'] = True
                vals['available_pricelist_ids'] = [Command.link(p.id) for p in valid_pricelists]
                default_pl = env['product.pricelist'].sudo().search([
                    ('company_id', 'in', [config.company_id.id, False]),
                    ('currency_id', '=', config.currency_id.id),
                    ('item_ids', '=', False),
                ], order='sequence asc, id asc', limit=1) or env['product.pricelist'].sudo().search([
                    ('name', '=', 'Default'),
                    ('company_id', 'in', [config.company_id.id, False]),
                    ('currency_id', '=', config.currency_id.id),
                ], limit=1) or valid_pricelists[:1]
                if default_pl:
                    vals['available_pricelist_ids'].append(Command.link(default_pl.id))
                    if not config.pricelist_id:
                        vals['pricelist_id'] = default_pl.id

        # 1. Take out / Delivery / Presets
        if hasattr(config, 'use_presets') and presets:
            vals['use_presets'] = True
            vals['available_preset_ids'] = [Command.set(presets.ids)]
            if is_restaurant:
                vals['default_preset_id'] = presets[0].id
            elif len(presets) > 1:
                vals['default_preset_id'] = presets[1].id

        # 2. Table Booking (Reservations)
        if is_restaurant and hasattr(config, 'use_booking') and app_type:
            vals['module_pos_appointment'] = True
            vals['use_booking'] = True
            vals['booking_appointment_type_id'] = app_type.id
            if hasattr(config, 'booking_no_show_grace_minutes'):
                vals['booking_no_show_grace_minutes'] = 15

        # 3. Mobile self-order & Kiosk
        if hasattr(config, 'self_ordering_mode'):
            if is_restaurant:
                vals['self_ordering_mode'] = 'mobile'
                vals['self_ordering_service_mode'] = 'table'
            else:
                vals['self_ordering_mode'] = 'kiosk'
                vals['self_ordering_service_mode'] = 'counter'
            if hasattr(config, 'self_ordering_pay_after'):
                vals['self_ordering_pay_after'] = 'meal'

        # 4. Tips configuration
        if hasattr(config, 'iface_tipproduct') and tip_prod:
            vals['iface_tipproduct'] = True
            vals['tip_product_id'] = tip_prod.id
            if hasattr(config, 'set_tip_after_payment'):
                vals['set_tip_after_payment'] = True
            if hasattr(config, 'tip_percentage_1'):
                vals['tip_percentage_1'] = 5
                vals['tip_percentage_2'] = 10
                vals['tip_percentage_3'] = 15

        # 5. Restrict categories
        if hasattr(config, 'limit_categories') and demo_cats:
            vals['limit_categories'] = True
            vals['iface_available_categ_ids'] = [Command.set(demo_cats.ids)]
            if hasattr(config, 'show_category_images'):
                vals['show_category_images'] = True

        try:
            config.write(vals)
            _logger.info("Hudson POS: Successfully configured all advanced options on POS '%s'", config.name)
        except Exception as e:
            _logger.warning("Could not update POS config %s: %s", config.name, e)

    # Link only valid loyalty programs (that have valid rewards) to active POS configs
    # Unlink any program without rewards to avoid JS ControlButtons crash
    if loyalty_progs:
        for prog in loyalty_progs:
            try:
                if prog.reward_ids:
                    prog.write({'pos_config_ids': [Command.set(configs.ids)]})
                else:
                    prog.write({'pos_config_ids': [Command.clear()]})
            except Exception:
                pass


def _configure_loyalty_demo_data(env):
    """
    Sets up complete, rich demo data for all 6 loyalty program types (+ Gift Card & eWallet):
    1. Coupons (coupons): Seasonal coupons with pre-generated codes COUPON15, BURGER50, FESTIVE20
    2. Loyalty Cards (loyalty): RestoCafe VIP Club with 3 reward tiers (5%, 10%, Free Lava Cake) and demo card VIP-CLUB-1001 with 150 points
    3. Promotions (promotion): Happy Hour, Welcome, Weekend, Family Combo
    4. Discount Code (promo_code): DISCOUNT10 (10% off order) and BURGER20 (20% off burgers)
    5. Buy X Get Y (buy_x_get_y): Buy 2 Burgers Get 1 Soft Drink Free, Buy 2 Hot Drinks Get 1 Cookie Free
    6. Next Order Coupons (next_order_coupons): Spend ₹500 Get 15% Off Next Order with demo card NEXTVISIT15
    7. Gift Cards (gift_card): Demo card GIFTCARD-100 (₹100 balance)
    8. eWallet (ewallet): Demo card EWALLET-500 (₹500 balance)
    """
    if 'loyalty.program' not in env:
        return

    LoyaltyProgram = env['loyalty.program'].sudo()
    LoyaltyCard = env['loyalty.card'].sudo()
    LoyaltyHistory = env['loyalty.history'].sudo() if 'loyalty.history' in env else False
    Product = env['product.product'].sudo()

    # Find products for rules and rewards
    bacon_burger = Product.search([('name', '=', 'Bacon Burger')], limit=1)
    cheese_burger = Product.search([('name', '=', 'Cheese Burger')], limit=1)
    coke = Product.search([('name', '=', 'Coca-Cola')], limit=1)
    espresso = Product.search([('name', '=', 'Espresso')], limit=1)
    green_tea = Product.search([('name', '=', 'Green Tea')], limit=1)
    ice_tea = Product.search([('name', '=', 'Ice Tea')], limit=1)
    cookie = Product.search([('name', '=', 'Double Chocolate Chip Cookie')], limit=1)
    cake = Product.search([('name', '=', 'Chocolate Lava Cake')], limit=1)

    burger_ids = [p.id for p in [bacon_burger, cheese_burger] if p]
    hot_drink_ids = [p.id for p in [espresso, green_tea, ice_tea] if p]

    def ensure_card(program, code, points, description='Demo Card', partner=False):
        if not program or not code:
            return
        card = False
        if partner and program.program_type == 'loyalty':
            card = LoyaltyCard.search([('program_id', '=', program.id), ('partner_id', '=', partner.id)], limit=1)
        if not card:
            card = LoyaltyCard.search([('code', '=', code)], limit=1)
        if not card:
            card = LoyaltyCard.create({
                'program_id': program.id,
                'code': code,
                'partner_id': partner.id if partner else False,
            })
        if card and points > card.points and 'loyalty.history' in env:
            diff = points - card.points
            env['loyalty.history'].sudo().create({
                'card_id': card.id,
                'description': description,
                'issued': diff,
            })
        return card

    # 1. Buy X Get Y: Burgers -> Soft Drink Free
    p_bxy_burger = LoyaltyProgram.search([('name', '=', 'Buy 2 Burgers, Get 1 Soft Drink Free')], limit=1)
    if not p_bxy_burger:
        p_bxy_burger = LoyaltyProgram.create({
            'name': 'Buy 2 Burgers, Get 1 Soft Drink Free',
            'program_type': 'buy_x_get_y',
            'trigger': 'auto',
            'applies_on': 'current',
            'portal_point_name': 'Credit(s)',
        })
    if p_bxy_burger:
        if not p_bxy_burger.rule_ids and burger_ids:
            p_bxy_burger.write({
                'rule_ids': [Command.create({
                    'reward_point_mode': 'unit',
                    'reward_point_amount': 1,
                    'minimum_qty': 2,
                    'product_ids': [Command.set(burger_ids)],
                })]
            })
        elif p_bxy_burger.rule_ids and burger_ids:
            p_bxy_burger.rule_ids[0].write({
                'reward_point_mode': 'unit',
                'reward_point_amount': 1,
                'minimum_qty': 2,
                'product_ids': [Command.set(burger_ids)],
            })
        if not p_bxy_burger.reward_ids and coke:
            p_bxy_burger.write({
                'reward_ids': [Command.create({
                    'reward_type': 'product',
                    'reward_product_id': coke.id,
                    'reward_product_qty': 1,
                    'required_points': 2,
                    'description': 'Free Coca-Cola with 2 Burgers',
                })]
            })
        elif p_bxy_burger.reward_ids and coke:
            p_bxy_burger.reward_ids[0].write({
                'reward_type': 'product',
                'reward_product_id': coke.id,
                'reward_product_qty': 1,
                'required_points': 2,
                'description': 'Free Coca-Cola with 2 Burgers',
            })

    # 2. Buy X Get Y: Hot Drinks -> Cookie Free
    p_bxy_coffee = LoyaltyProgram.search([('name', '=', 'Buy 2 Hot Drinks, Get 1 Cookie Free')], limit=1)
    if not p_bxy_coffee:
        p_bxy_coffee = LoyaltyProgram.create({
            'name': 'Buy 2 Hot Drinks, Get 1 Cookie Free',
            'program_type': 'buy_x_get_y',
            'trigger': 'auto',
            'applies_on': 'current',
            'portal_point_name': 'Credit(s)',
        })
    if p_bxy_coffee:
        if not p_bxy_coffee.rule_ids and hot_drink_ids:
            p_bxy_coffee.write({
                'rule_ids': [Command.create({
                    'reward_point_mode': 'unit',
                    'reward_point_amount': 1,
                    'minimum_qty': 2,
                    'product_ids': [Command.set(hot_drink_ids)],
                })]
            })
        elif p_bxy_coffee.rule_ids and hot_drink_ids:
            p_bxy_coffee.rule_ids[0].write({
                'reward_point_mode': 'unit',
                'reward_point_amount': 1,
                'minimum_qty': 2,
                'product_ids': [Command.set(hot_drink_ids)],
            })
        if not p_bxy_coffee.reward_ids and cookie:
            p_bxy_coffee.write({
                'reward_ids': [Command.create({
                    'reward_type': 'product',
                    'reward_product_id': cookie.id,
                    'reward_product_qty': 1,
                    'required_points': 2,
                    'description': 'Free Cookie with 2 Hot Drinks',
                })]
            })
        elif p_bxy_coffee.reward_ids and cookie:
            p_bxy_coffee.reward_ids[0].write({
                'reward_type': 'product',
                'reward_product_id': cookie.id,
                'reward_product_qty': 1,
                'required_points': 2,
                'description': 'Free Cookie with 2 Hot Drinks',
            })

    # 3. Discount Code: BURGER20 - link to burger products
    p_burger20 = LoyaltyProgram.search([('name', '=', 'Discount Code: BURGER20 — 20% Off Burgers')], limit=1)
    if p_burger20 and burger_ids:
        if p_burger20.rule_ids:
            p_burger20.rule_ids[0].write({'product_ids': [Command.set(burger_ids)]})
        if p_burger20.reward_ids:
            p_burger20.reward_ids[0].write({
                'discount_applicability': 'specific',
                'discount_product_ids': [Command.set(burger_ids)],
            })

    # 4. Loyalty Points: Add Tier 3 free dessert reward
    p_loyalty = LoyaltyProgram.search([('program_type', '=', 'loyalty')], limit=1)
    if p_loyalty and cake:
        free_cake_reward = p_loyalty.reward_ids.filtered(lambda r: r.reward_type == 'product')
        if not free_cake_reward:
            p_loyalty.write({
                'reward_ids': [Command.create({
                    'reward_type': 'product',
                    'reward_product_id': cake.id,
                    'reward_product_qty': 1,
                    'required_points': 150,
                    'description': 'Free Chocolate Lava Cake for 150 Points',
                })]
            })

    # 5. Pre-generate active demo cards for all programs
    p_coupon = LoyaltyProgram.search([('name', '=', 'Seasonal Discount Coupons — 15% Off')], limit=1)
    if p_coupon:
        ensure_card(p_coupon, 'COUPON15', 1, 'Seasonal 15% Off Coupon')
        ensure_card(p_coupon, 'BURGER50', 1, 'Burger Season Coupon')
        ensure_card(p_coupon, 'FESTIVE20', 1, 'Festive Celebration Coupon')

    p_next = LoyaltyProgram.search([('name', '=', 'Spend ₹500, Get 15% Off Next Order')], limit=1)
    if p_next:
        ensure_card(p_next, 'NEXTVISIT15', 1, 'Next Visit 15% Off Coupon')

    # Dedicated demo VIP partner for loyalty card testing
    vip_partner = env['res.partner'].sudo().search([('name', '=', 'VIP Customer (Demo)')], limit=1)
    if not vip_partner:
        vip_partner = env['res.partner'].sudo().create({
            'name': 'VIP Customer (Demo)',
            'email': 'vip.demo@example.com',
            'phone': '+91 98470 99999',
            'customer_rank': 1,
        })

    if p_loyalty:
        ensure_card(p_loyalty, 'VIP-CLUB-1001', 150, 'RestoCafe VIP Demo Card', partner=vip_partner)

    p_gc = LoyaltyProgram.search([('program_type', '=', 'gift_card')], limit=1)
    if p_gc:
        ensure_card(p_gc, 'GIFTCARD-100', 100, 'Demo Gift Card ₹100')

    p_ew = LoyaltyProgram.search([('program_type', '=', 'ewallet')], limit=1)
    if p_ew:
        ensure_card(p_ew, 'EWALLET-500', 500, 'Demo eWallet ₹500', partner=vip_partner)

    _logger.info("Hudson POS: Successfully configured rich demo data for all 6 Loyalty & Discount program types.")


def _load_stock_inventory(env):
    """
    Ensures POS storable products have positive inventory on hand in the main internal stock location.
    """
    StockLocation = env['stock.location'].sudo()
    StockQuant = env['stock.quant'].sudo()
    ProductProduct = env['product.product'].sudo()

    stock_location = StockLocation.search([
        ('usage', '=', 'internal'),
        ('company_id', 'in', [env.company.id, False])
    ], order='id asc', limit=1)

    if not stock_location:
        return

    pos_products = ProductProduct.search([
        ('available_in_pos', '=', True),
        ('is_storable', '=', True),
    ])

    target_qty = 100.0
    for prod in pos_products:
        quant = StockQuant.search([
            ('product_id', '=', prod.id),
            ('location_id', '=', stock_location.id)
        ], limit=1)

        current_qty = quant.quantity if quant else 0.0
        if current_qty < 20.0:
            diff = target_qty - current_qty
            try:
                StockQuant._update_available_quantity(prod, stock_location, diff)
            except Exception:
                pass


def _load_recruitment_demo_data(env):
    """
    Ensures Restaurant & Cafe recruitment job openings are active, published to the website,
    and populated with sample applicants across hiring pipeline stages.
    """
    _logger.info("Hudson POS: Verifying recruitment demo data and website job publishing...")

    if 'hr.job' not in env:
        _logger.warning("Hudson POS: hr.job model not available, skipping recruitment demo data.")
        return

    HrJob = env['hr.job'].sudo()
    demo_job_xml_ids = [
        'job_resto_chef',
        'job_resto_supervisor',
        'job_barista',
        'job_service_captain',
    ]

    for xml_id in demo_job_xml_ids:
        job = env.ref(f'hudson_pos_demo_data.{xml_id}', raise_if_not_found=False)
        if job and job.exists():
            write_vals = {}
            if hasattr(job, 'is_published') and not job.is_published:
                write_vals['is_published'] = True
            if hasattr(job, 'website_published') and not job.website_published:
                write_vals['website_published'] = True
            if hasattr(job, 'active') and not job.active:
                write_vals['active'] = True
            if write_vals:
                try:
                    job.write(write_vals)
                except Exception as e:
                    _logger.warning("Could not set published state for job %s: %s", job.name, e)

    _logger.info("Hudson POS: Recruitment demo data published to website successfully.")


def _load_kitchen_display_demo_data(env):
    """
    Deprecated no-op: Kitchen Display demo configurations were removed from
    hudson_pos_demo_data. A single editable default Kitchen Display is now
    created on install by hudson_kitchen_display.
    """
    _logger.info("Hudson POS: Kitchen Display demo data disabled (handled by hudson_kitchen_display).")
    return []


def _load_sample_pos_orders(env):
    """
    Creates sample closed POS orders to demonstrate the reporting and order history
    for the Restaurant POS. Orders are created in 'done' state without opening a session.
    """
    _logger.info("Hudson POS: Creating sample POS orders...")

    if 'pos.order' not in env:
        _logger.warning("Hudson POS: pos.order model not available. Skipping sample orders.")
        return

    PosConfig = env['pos.config'].sudo()
    PosOrder = env['pos.order'].sudo()
    PosSession = env['pos.session'].sudo()
    ProductProduct = env['product.product'].sudo()

    # Only create if no orders exist yet
    existing_orders = PosOrder.search([], limit=1)
    if existing_orders:
        _logger.info("Hudson POS: POS orders already exist, skipping sample order creation.")
        return

    # Get the Restaurant POS config
    resto_config = PosConfig.search([('name', '=', 'Restaurant')], limit=1)
    if not resto_config:
        _logger.warning("Hudson POS: Restaurant POS config not found. Skipping sample orders.")
        return

    # We need a session to create orders - create a rescue/demo session
    # Check if there's an open session
    open_session = PosSession.search([
        ('config_id', '=', resto_config.id),
        ('state', 'in', ['opening_control', 'opened']),
    ], limit=1)

    if open_session:
        _logger.info("Hudson POS: POS session already open, skipping sample orders to avoid conflicts.")
        return

    # Get sample products
    def find_product(name):
        prod = ProductProduct.search([('name', '=', name), ('available_in_pos', '=', True)], limit=1)
        return prod

    sample_order_defs = [
        {
            'xml_id': 'sample_order_table1_dinner',
            'name': 'Table 01 — Dinner',
            'lines': [
                ('Cheese Burger', 2, 320.0),
                ('Coca-Cola', 2, 65.0),
                ('Warm Apple Pie', 1, 180.0),
            ],
        },
        {
            'xml_id': 'sample_order_table2_lunch',
            'name': 'Table 02 — Lunch',
            'lines': [
                ('Pasta Bolognese', 2, 290.0),
                ('Fanta', 2, 60.0),
            ],
        },
        {
            'xml_id': 'sample_order_table3_breakfast',
            'name': 'Table 03 — Cafe Order',
            'lines': [
                ('Espresso', 2, 85.0),
                ('Artisan Chocolate Croissant', 2, 120.0),
            ],
        },
        {
            'xml_id': 'sample_order_table4_sushi',
            'name': 'Table 04 — Special',
            'lines': [
                ('Lunch Maki 18pc', 1, 450.0),
                ('Green Tea', 2, 75.0),
                ('New York Cheesecake', 2, 220.0),
            ],
        },
        {
            'xml_id': 'sample_order_table5_pizza',
            'name': 'Table 05 — Evening',
            'lines': [
                ('Pizza Margherita', 1, 380.0),
                ('Milkshake Banana', 1, 150.0),
                ('Tiramisu', 1, 190.0),
            ],
        },
    ]

    # Try to create a temporary session to place orders
    try:
        from datetime import datetime, timedelta

        # Create session directly
        session = PosSession.create({'config_id': resto_config.id})

        # Set state to 'opened' directly (safe for demo data initialization)
        session.write({
            'state': 'opened',
            'start_at': datetime.now() - timedelta(days=1),
        })

        base_date = datetime.now() - timedelta(days=1)
        created_count = 0

        for i, order_def in enumerate(sample_order_defs):
            # Check if already created via ir.model.data
            existing = env.ref(
                f"hudson_pos_demo_data.{order_def['xml_id']}",
                raise_if_not_found=False
            )
            if existing and existing.exists():
                continue

            order_lines = []
            total = 0.0
            for prod_name, qty, price in order_def['lines']:
                prod = find_product(prod_name)
                if not prod:
                    _logger.warning("Hudson POS: Product not found: %s", prod_name)
                    continue
                subtotal = qty * price
                total += subtotal
                order_lines.append((0, 0, {
                    'product_id': prod.id,
                    'qty': qty,
                    'price_unit': price,
                    'price_subtotal': subtotal,
                    'price_subtotal_incl': subtotal,
                }))

            if not order_lines:
                continue

            order_date = base_date - timedelta(hours=i * 2)

            try:
                order = PosOrder.create({
                    'name': order_def['name'],
                    'session_id': session.id,
                    'config_id': resto_config.id,
                    'date_order': order_date,
                    'lines': order_lines,
                    'state': 'paid',
                    'amount_total': total,
                    'amount_paid': total,
                    'amount_tax': 0.0,
                    'amount_return': 0.0,
                })

                # Register in ir.model.data
                env['ir.model.data'].sudo().create({
                    'module': 'hudson_pos_demo_data',
                    'name': order_def['xml_id'],
                    'model': 'pos.order',
                    'res_id': order.id,
                    'noupdate': True,
                })
                created_count += 1
                _logger.info("Hudson POS: Created sample order '%s' (total=%.2f)", order_def['name'], total)

            except Exception as e:
                _logger.warning("Hudson POS: Could not create sample order '%s': %s", order_def['name'], e)

        # Close the session cleanly
        try:
            session.write({'state': 'closed', 'stop_at': datetime.now()})
        except Exception as e:
            _logger.warning("Hudson POS: Could not close demo session: %s", e)

        _logger.info("Hudson POS: Created %d sample POS orders successfully.", created_count)

    except Exception as e:
        _logger.error("Hudson POS: Failed to create sample POS session/orders: %s", e)
        import traceback
        _logger.error(traceback.format_exc())


def clear_pos_demo_data(env):
    """
    Cleanly clears demo data records created under hudson_pos_demo_data.
    """
    _logger.info("Hudson POS: Starting safe demo data cleanup...")

    # 0. First, clear HINV- Inventory Suite (BoMs, Reordering Rules, POs, Transfers, Ingredients, Packaging, Locations, Vendors)
    # Existing Restaurant & Cafe POS products are preserved cleanly by clear_inventory_suite_demo_data.
    try:
        from .demo_inventory_suite import clear_inventory_suite_demo_data
        clear_inventory_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not clear Inventory suite demo data: %s", e)

    # 1. Next, clear Business Suite (Sales, Purchase, MRP, Events, Maintenance, Survey)
    # This cleanly removes orders/BOMs referencing demo products before product deletion.
    try:
        from .demo_business_suite import clear_business_suite_demo_data
        clear_business_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not clear Business suite demo data: %s", e)

    # 2. Clear sample POS orders and combo items referencing demo products
    try:
        with env.cr.savepoint():
            demo_imd_orders = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('model', '=', 'pos.order'),
            ])
            order_ids = [d.res_id for d in demo_imd_orders]
            demo_orders = env['pos.order'].sudo().browse(order_ids).exists() if order_ids else env['pos.order'].sudo()
            sample_orders = demo_orders | env['pos.order'].sudo().search([
                ('pos_reference', 'like', 'Order 00001-')
            ])
            if sample_orders:
                non_cancelled = sample_orders.filtered(lambda o: o.state not in ('draft', 'cancel'))
                if non_cancelled:
                    non_cancelled.write({'state': 'cancel'})
                sample_orders.mapped('lines').unlink()
                sample_orders.unlink()
    except Exception as e:
        _logger.warning("Could not unlink sample POS orders: %s", e)

    try:
        with env.cr.savepoint():
            demo_imd_tmpls = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('model', '=', 'product.template')
            ])
            tmpl_ids = [d.res_id for d in demo_imd_tmpls]
            if tmpl_ids and 'product.combo.item' in env:
                variants = env['product.product'].sudo().search([('product_tmpl_id', 'in', tmpl_ids)])
                if variants:
                    combo_items = env['product.combo.item'].sudo().search([('product_id', 'in', variants.ids)])
                    combos = combo_items.mapped('combo_id')
                    combo_items.unlink()
                    empty_demo_combos = combos.filtered(
                        lambda c: not c.combo_item_ids and c.name in [
                            'Burgers', 'Drinks', 'Sushi Choices', 'Pasta Choices', 'Dessert Choices'
                        ]
                    )
                    if empty_demo_combos:
                        empty_demo_combos.unlink()
    except Exception as e:
        _logger.warning("Could not unlink demo combo items: %s", e)

    # 3. Clear HR Suite (Payroll, Leaves, Attendance, Fleet, Lunch, Expenses, Employees)
    try:
        from .demo_hr_suite import clear_hr_suite_demo_data
        clear_hr_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not clear HR suite demo data: %s", e)

    # 4. Clear stock quants
    try:
        with env.cr.savepoint():
            demo_imd_tmpls = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('model', '=', 'product.template')
            ])
            tmpl_ids = [d.res_id for d in demo_imd_tmpls]
            if tmpl_ids:
                variants = env['product.product'].sudo().search([('product_tmpl_id', 'in', tmpl_ids)])
                if variants:
                    quants = env['stock.quant'].sudo().search([('product_id', 'in', variants.ids)])
                    if quants:
                        quants.unlink()
    except Exception as e:
        _logger.warning("Could not unlink quants: %s", e)

    # 4b. Cleanup demo loyalty cards
    if 'loyalty.card' in env:
        try:
            with env.cr.savepoint():
                demo_codes = ['COUPON15', 'BURGER50', 'FESTIVE20', 'NEXTVISIT15', 'VIP-CLUB-1001', 'GIFTCARD-100', 'EWALLET-500']
                env['loyalty.card'].sudo().search([('code', 'in', demo_codes)]).unlink()
        except Exception:
            pass

    # 5. Ordered removal of XML demo records
    models_order = [
        'hr.applicant',
        'hr.job',
        'hr.department',
        'slide.slide',
        'slide.channel',
        'pos.order',
        'pos.prep.display',
        'product.combo',
        'restaurant.table',
        'restaurant.floor',
        'product.template',
        'pos.category',
        'pos.course',
        'pos.note',
        'product.tag',
        'product.pricelist',
        'loyalty.program',
    ]

    for model_name in models_order:
        data_records = env['ir.model.data'].sudo().search([
            ('module', '=', 'hudson_pos_demo_data'),
            ('model', '=', model_name)
        ])
        for data in data_records:
            try:
                with env.cr.savepoint():
                    rec = env[model_name].sudo().browse(data.res_id)
                    if rec.exists():
                        rec.unlink()
            except Exception:
                try:
                    with env.cr.savepoint():
                        rec = env[model_name].sudo().browse(data.res_id)
                        if rec.exists() and hasattr(rec, 'active'):
                            rec.write({'active': False})
                        if rec.exists() and hasattr(rec, 'available_in_pos'):
                            rec.write({'available_in_pos': False})
                except Exception:
                    pass

        try:
            with env.cr.savepoint():
                data_records.unlink()
        except Exception:
            pass

    # 6. Ensure remaining POS configs do not retain missing/empty pricelist state
    try:
        with env.cr.savepoint():
            for cfg in env['pos.config'].sudo().search([('use_pricelist', '=', True)]):
                if not cfg.pricelist_id or not cfg.pricelist_id.active:
                    fallback_pl = env['product.pricelist'].sudo().search([
                        ('company_id', 'in', [cfg.company_id.id, False]),
                        ('currency_id', '=', cfg.currency_id.id),
                    ], order='sequence asc, id asc', limit=1)
                    if fallback_pl:
                        write_pl = {'pricelist_id': fallback_pl.id}
                        if fallback_pl not in cfg.available_pricelist_ids:
                            write_pl['available_pricelist_ids'] = [Command.link(fallback_pl.id)]
                        cfg.write(write_pl)
                    else:
                        cfg.write({'use_pricelist': False, 'pricelist_id': False})
    except Exception as e:
        _logger.warning("Could not sanitize POS pricelists after demo cleanup: %s", e)

    _logger.info("Hudson POS: Demo data cleared safely.")
    return True
