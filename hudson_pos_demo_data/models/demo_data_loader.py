# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import base64
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
    'demo/elearning_demo.xml',
]

IMAGE_SEARCH_PATHS = [
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
    'Signature Hot Chocolate': 'soft-drink-icon.png',
    'Warm Apple Pie': 'product_apple_pie.png',
    'Artisan Chocolate Croissant': 'product_pain_au_chocolat.png',
    'Double Chocolate Chip Cookie': 'product_blueberry_muffin.png',
    'New York Cheesecake': 'product_pecan_pie.png',
    'Chocolate Lava Cake': 'pastries-icon.png',
    'Crème Brûlée': 'pastries-icon.png',
    'Tiramisu': 'pastries-icon.png',
    'Fresh Strawberry Tart': 'product_cherry_pie.png',
    'Vanilla Bean Ice Cream Sundae': 'th-milkshake_banana.png',
    'French Macarons Box (6 pcs)': 'pastries-icon.png',
    'Belgian Milk Chocolate Truffles': 'pastries-icon.png',
    'Dark Chocolate Bar 70%': 'pastries-icon.png',
    'White Chocolate Raspberry Bar': 'pastries-icon.png',
    'Luxury Chocolate Gift Box': 'pastries-icon.png',
    'Dessert & Hot Drink Combo': 'pastries-icon.png',
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
    _cleanup_duplicate_floors(env)

    # 2. Pre-bind existing records to ir.model.data
    _pre_bind_existing_records(env)

    # 3. Execute all standard XML demo files
    for xml_file in DEMO_XML_FILES:
        try:
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
    _cleanup_duplicate_floors(env)

    # 5. Configure graphical floor layouts and table positions
    _configure_floors_and_tables(env)

    # 6. Ensure Restaurant and Cafe POS configurations exist
    _ensure_default_shops(env)

    # 7. Configure true POS Combos (product.combo & type='combo')
    _configure_combos(env)

    # 8. Attach images to products
    _load_product_images(env)

    # 9. Link floors, screens, pricelists, and loyalty programs to POS configs
    _post_process_pos_configs(env, pos_config_ids)

    # 10. Initialize stock inventory
    _load_stock_inventory(env)

    # 11. Configure & publish recruitment job openings & sample applicants
    _load_recruitment_demo_data(env)

    # 12. Configure & publish eLearning courses to website
    _load_elearning_demo_data(env)

    # 13. Create Kitchen Display (KDS) sample configurations
    _load_kitchen_display_demo_data(env)

    # 14. Create sample POS orders for demonstration
    _load_sample_pos_orders(env)

    # 15. Create full connected HR Suite demo data (Employees, Attendance, Time Off, Fleet, Lunch, Expenses, Payroll)
    try:
        from .demo_hr_suite import load_hr_suite_demo_data
        load_hr_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load HR suite demo data: %s", e)

    # 16. Create full connected Business Suite demo data (CRM, Sales, Inventory, Purchase, MRP, Maintenance, Events, Survey)
    try:
        from .demo_business_suite import load_business_suite_demo_data
        load_business_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Business suite demo data: %s", e)

    _logger.info("Hudson POS: Restaurant & Cafe demo data loaded successfully.")
    return True


def _cleanup_duplicate_floors(env):
    """
    Removes auto-generated dummy floors named 'My Company' and orphan floors without POS configs.
    """
    RestaurantFloor = env['restaurant.floor'].sudo()
    dummy_floors = RestaurantFloor.search([('name', '=', 'My Company')])
    for flr in dummy_floors:
        try:
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


def _load_product_images(env):
    """
    Attaches high-resolution product images to food, drink, and dessert products.
    """
    ProductTemplate = env['product.template'].sudo()

    def get_image_base64(filename):
        for base_dir in IMAGE_SEARCH_PATHS:
            full_path = os.path.join(base_dir, filename)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'rb') as f:
                        return base64.b64encode(f.read()).decode('utf-8')
                except Exception:
                    pass
        return None

    for prod_name, img_filename in PRODUCT_IMAGE_MAP.items():
        tmpl = ProductTemplate.search([('name', '=', prod_name)], limit=1)
        if tmpl and not tmpl.image_1920:
            img_b64 = get_image_base64(img_filename)
            if img_b64:
                try:
                    tmpl.write({'image_1920': img_b64})
                except Exception as e:
                    _logger.warning("Could not set image on %s: %s", prod_name, e)


def _pre_bind_existing_records(env):
    """
    Maps existing records to their XML IDs in ir.model.data to ensure
    convert_file performs updates instead of duplicate inserts.
    """
    def bind_xml(model, xml_name, domain):
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
        ('loyalty_program_weekend_special', 'Weekend Special — Buy 2 Get 1 Free (Drinks)'),
        ('loyalty_program_points', 'RestoCafe Loyalty Points'),
        ('loyalty_program_family_combo', 'Family Combo — 20% Off Orders Above ₹500'),
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

    # Tip Product
    tip_prod = env['product.product'].sudo().search([('name', '=', 'Tips')], limit=1)
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
                vals['use_pricelist'] = True
                vals['available_pricelist_ids'] = [Command.link(p.id) for p in valid_pricelists]
                if not config.pricelist_id:
                    default_pl = env['product.pricelist'].sudo().search([('name', '=', 'Default')], limit=1) or valid_pricelists[:1]
                    if default_pl:
                        vals['pricelist_id'] = default_pl.id
                        vals['available_pricelist_ids'].append(Command.link(default_pl.id))

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


def _load_elearning_demo_data(env):
    """
    Ensures Restaurant & Cafe eLearning courses (slide.channel) are active,
    published to the website, and have sample lesson slides (slide.slide).
    """
    _logger.info("Hudson POS: Verifying eLearning demo data and website course publishing...")

    if 'slide.channel' not in env:
        _logger.warning("Hudson POS: slide.channel model not available, skipping eLearning demo data.")
        return

    SlideChannel = env['slide.channel'].sudo()

    demo_channel_xml_ids = [
        'slide_channel_kerala_cuisine',
        'slide_channel_barista_coffee',
        'slide_channel_restaurant_ops',
        'slide_channel_food_safety',
    ]

    # Clean up any dummy website page intercepting /slides
    if 'website.page' in env:
        dummy_pages = env['website.page'].sudo().search([('url', '=', '/slides')])
        for dp in dummy_pages:
            try:
                dp.unlink()
            except Exception:
                pass

    for xml_id in demo_channel_xml_ids:
        channel = env.ref(f'hudson_pos_demo_data.{xml_id}', raise_if_not_found=False)
        if channel and channel.exists():
            write_vals = {
                'channel_type': 'training',
                'visibility': 'public',
                'enroll': 'public',
            }
            if hasattr(channel, 'is_published') and not channel.is_published:
                write_vals['is_published'] = True
            if hasattr(channel, 'active') and not channel.active:
                write_vals['active'] = True
            try:
                channel.write(write_vals)
                _logger.info("Hudson POS: Published eLearning channel: %s", channel.name)
            except Exception as e:
                _logger.warning("Could not publish eLearning channel %s: %s", channel.name, e)
        else:
            _logger.warning("Hudson POS: eLearning channel XML ID not found: %s", xml_id)

    # Also ensure all lesson slides are published
    if 'slide.slide' in env:
        SlidePage = env['slide.slide'].sudo()
        demo_channel_ids = []
        for xml_id in demo_channel_xml_ids:
            channel = env.ref(f'hudson_pos_demo_data.{xml_id}', raise_if_not_found=False)
            if channel and channel.exists():
                demo_channel_ids.append(channel.id)

        if demo_channel_ids:
            unpublished_slides = SlidePage.search([
                ('channel_id', 'in', demo_channel_ids),
                ('is_published', '=', False),
            ])
            if unpublished_slides:
                try:
                    unpublished_slides.write({'is_published': True})
                    _logger.info("Hudson POS: Published %d eLearning slides.", len(unpublished_slides))
                except Exception as e:
                    _logger.warning("Could not publish eLearning slides: %s", e)

    _logger.info("Hudson POS: eLearning demo data published to website successfully.")


def _load_kitchen_display_demo_data(env):
    """
    Creates sample Kitchen Display (KDS) configurations linked to the Restaurant POS.
    Uses the hudson_kitchen_display module's pos.prep.display model.
    """
    _logger.info("Hudson POS: Setting up Kitchen Display demo data...")

    if 'pos.prep.display' not in env:
        _logger.warning("Hudson POS: pos.prep.display model not available. Skipping KDS setup.")
        return

    PrepDisplay = env['pos.prep.display'].sudo()
    PosConfig = env['pos.config'].sudo()
    PosCategory = env['pos.category'].sudo()

    # Find Restaurant POS config
    resto_config = PosConfig.search([('name', '=', 'Restaurant')], limit=1)

    # Find Food and Drinks categories for category filtering
    food_cat = PosCategory.search([('name', '=', 'Food')], limit=1)
    drinks_cat = PosCategory.search([('name', '=', 'Drinks')], limit=1)

    kds_configs = [
        {
            'name': 'Main Kitchen Display',
            'xml_id': 'kds_main_kitchen',
            'category_ids': food_cat.ids if food_cat else [],
            'auto_clear': False,
            'stages': [
                {'name': 'New Order', 'sequence': 1, 'color': '#E74C3C', 'alert_timer': 15},
                {'name': 'Cooking', 'sequence': 2, 'color': '#F39C12', 'alert_timer': 10},
                {'name': 'Ready to Serve', 'sequence': 3, 'color': '#27AE60', 'alert_timer': 5},
                {'name': 'Served', 'sequence': 4, 'color': '#95A5A6', 'alert_timer': 0},
            ],
        },
        {
            'name': 'Bar & Drinks Display',
            'xml_id': 'kds_bar_drinks',
            'category_ids': drinks_cat.ids if drinks_cat else [],
            'auto_clear': True,
            'stages': [
                {'name': 'Preparing', 'sequence': 1, 'color': '#3498DB', 'alert_timer': 8},
                {'name': 'Ready', 'sequence': 2, 'color': '#1ABC9C', 'alert_timer': 3},
                {'name': 'Collected', 'sequence': 3, 'color': '#BDC3C7', 'alert_timer': 0},
            ],
        },
        {
            'name': 'Expediter / Pass Display',
            'xml_id': 'kds_expediter',
            'category_ids': [],
            'auto_clear': False,
            'stages': [
                {'name': 'Waiting', 'sequence': 1, 'color': '#9B59B6', 'alert_timer': 20},
                {'name': 'Plating', 'sequence': 2, 'color': '#E67E22', 'alert_timer': 5},
                {'name': 'Pass Ready', 'sequence': 3, 'color': '#2ECC71', 'alert_timer': 2},
                {'name': 'Dispatched', 'sequence': 4, 'color': '#95A5A6', 'alert_timer': 0},
            ],
        },
    ]

    for kds_def in kds_configs:
        # Check if already exists via ir.model.data
        existing = env.ref(
            f"hudson_pos_demo_data.{kds_def['xml_id']}",
            raise_if_not_found=False
        )
        if existing and existing.exists():
            _logger.info("Hudson POS: KDS '%s' already exists, skipping.", kds_def['name'])
            continue

        # Check by name
        existing_by_name = PrepDisplay.search([('name', '=', kds_def['name'])], limit=1)
        if existing_by_name:
            # Bind to ir.model.data
            imd = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('name', '=', kds_def['xml_id']),
            ], limit=1)
            if not imd:
                env['ir.model.data'].sudo().create({
                    'module': 'hudson_pos_demo_data',
                    'name': kds_def['xml_id'],
                    'model': 'pos.prep.display',
                    'res_id': existing_by_name.id,
                    'noupdate': True,
                })
            continue

        try:
            # Build stage data
            stage_vals = [(0, 0, {
                'name': s['name'],
                'sequence': s['sequence'],
                'color': s['color'],
                'alert_timer': s['alert_timer'],
            }) for s in kds_def['stages']]

            create_vals = {
                'name': kds_def['name'],
                'auto_clear': kds_def['auto_clear'],
                'stage_ids': stage_vals,
            }

            if kds_def['category_ids']:
                create_vals['category_ids'] = [(6, 0, kds_def['category_ids'])]

            if resto_config:
                create_vals['pos_config_ids'] = [(6, 0, [resto_config.id])]

            display = PrepDisplay.create(create_vals)

            # Register in ir.model.data for cleanup tracking
            env['ir.model.data'].sudo().create({
                'module': 'hudson_pos_demo_data',
                'name': kds_def['xml_id'],
                'model': 'pos.prep.display',
                'res_id': display.id,
                'noupdate': True,
            })

            _logger.info("Hudson POS: Created KDS '%s' (id=%d)", display.name, display.id)

        except Exception as e:
            _logger.error("Hudson POS: Failed to create KDS '%s': %s", kds_def['name'], e)

    _logger.info("Hudson POS: Kitchen Display demo data setup complete.")


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

    # 1. First, clear Business Suite (Sales, Purchase, MRP, Events, Maintenance, Survey)
    # This cleanly removes orders/BOMs referencing demo products before product deletion.
    try:
        from .demo_business_suite import clear_business_suite_demo_data
        clear_business_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not clear Business suite demo data: %s", e)

    # 2. Clear sample POS orders and order lines referencing demo products
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
                    pos_lines = env['pos.order.line'].sudo().search([('product_id', 'in', variants.ids)])
                    if pos_lines:
                        orders = pos_lines.mapped('order_id')
                        pos_lines.unlink()
                        if orders:
                            orders.unlink()
            sample_orders = env['pos.order'].sudo().search([
                ('pos_reference', 'like', 'Order 00001-')
            ])
            if sample_orders:
                sample_orders.lines.unlink()
                sample_orders.unlink()
    except Exception as e:
        _logger.warning("Could not unlink sample POS orders: %s", e)

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

    _logger.info("Hudson POS: Demo data cleared safely.")
    return True
