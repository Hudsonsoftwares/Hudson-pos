# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Manufacturing & Shop Floor demo data (central kitchen / bakery).

Creates, idempotently (records bound to xmlids of this module, prefix rc_mrp_):
  * 7 kitchen work centers (hot kitchen, grill, pizza oven, pastry, cold kitchen & sushi, beverage bar,
    packing & dispatch) with hourly costs, efficiency, OEE targets, setup/clean-up times
  * Operations (routings) on the 18 Resto Cafe bills of materials created by the Inventory suite
  * 14 manufacturing orders: draft, confirmed (ready and waiting for components), in progress with
    operators timing work orders live on the Shop Floor, paused, to close, done (with time logs,
    consumed components and backdated dates) and cancelled
  * A closed "Equipment Failure" downtime on the pizza oven, so OEE / losses reports show data
"""
import logging
from datetime import timedelta

from odoo import Command, fields

from .demo_guard import preexisting

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'


# --------------------------------------------------------------------------- helpers
def _ref(env, xid):
    return env.ref(f'{MODULE}.{xid}', raise_if_not_found=False)


def _bind(env, xid, record):
    env['ir.model.data'].sudo().create({
        'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
    })
    return record


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().create(vals))


def _now():
    return fields.Datetime.now().replace(second=0, microsecond=0)


def _employee(env, name):
    return env['hr.employee'].sudo().search([('name', '=', name)], limit=1) if 'hr.employee' in env else False


# --------------------------------------------------------------------------- work centers
# xid slug, name, code, cost/h, efficiency %, OEE target, setup min, clean-up min, color
WORKCENTERS = [
    ('hot_kitchen', 'Hot Kitchen Line', 'HOT', 22.0, 100, 85, 10, 15, 1),
    ('grill', 'Grill & Burger Station', 'GRL', 18.0, 105, 85, 5, 10, 2),
    ('pizza_oven', 'Pizza Stone Oven', 'PZA', 20.0, 100, 80, 15, 10, 3),
    ('pastry', 'Pastry & Dessert Station', 'PST', 16.0, 95, 85, 10, 10, 4),
    ('cold_kitchen', 'Cold Kitchen & Sushi Bar', 'CLD', 17.0, 100, 85, 5, 10, 5),
    ('beverage', 'Beverage & Coffee Bar', 'BEV', 12.0, 110, 90, 2, 5, 6),
    ('packing', 'Packing & Dispatch', 'PCK', 10.0, 100, 90, 0, 5, 7),
]

# product name -> [(operation, workcenter slug, minutes per unit)]
ROUTINGS = {
    'Cheese Burger': [('Grill patties', 'grill', 6), ('Assemble burger', 'grill', 2), ('Box & label', 'packing', 1)],
    'Bacon Burger': [('Grill patties & bacon', 'grill', 7), ('Assemble burger', 'grill', 2), ('Box & label', 'packing', 1)],
    'Pizza Margherita': [('Stretch dough & top', 'pizza_oven', 3), ('Bake in stone oven', 'pizza_oven', 6), ('Cut & box', 'packing', 1)],
    'Pizza Vegetarian': [('Stretch dough & top', 'pizza_oven', 4), ('Bake in stone oven', 'pizza_oven', 6), ('Cut & box', 'packing', 1)],
    'Pasta Bolognese': [('Cook pasta & ragu', 'hot_kitchen', 8), ('Portion & pack', 'packing', 1)],
    'Pasta 4 Formaggi': [('Cook pasta & cheese sauce', 'hot_kitchen', 7), ('Portion & pack', 'packing', 1)],
    'Club Sandwich': [('Prepare fillings', 'cold_kitchen', 4), ('Assemble & toast', 'grill', 3), ('Wrap & label', 'packing', 1)],
    'Spicy Tuna Sandwich': [('Prepare tuna mix', 'cold_kitchen', 3), ('Assemble & toast', 'grill', 2), ('Wrap & label', 'packing', 1)],
    'Lunch Maki 18pc': [('Cook & season sushi rice', 'cold_kitchen', 4), ('Roll & cut maki', 'cold_kitchen', 6), ('Box & label', 'packing', 1)],
    'Salmon and Avocado': [('Cook & season sushi rice', 'cold_kitchen', 3), ('Roll & cut', 'cold_kitchen', 5), ('Box & label', 'packing', 1)],
    'Espresso': [('Grind & pull shot', 'beverage', 1)],
    'Green Tea': [('Steep tea', 'beverage', 2)],
    'Milkshake Banana': [('Blend milkshake', 'beverage', 2), ('Cap & label', 'packing', 1)],
    'Tiramisu': [('Whip mascarpone cream', 'pastry', 3), ('Layer & set', 'pastry', 4), ('Portion & pack', 'packing', 1)],
    'New York Cheesecake': [('Mix & bake cheesecake', 'pastry', 6), ('Chill & portion', 'pastry', 2), ('Pack', 'packing', 1)],
    'Chocolate Lava Cake': [('Mix batter & fill moulds', 'pastry', 3), ('Bake', 'pastry', 4), ('Pack', 'packing', 1)],
    'Warm Apple Pie': [('Make pastry & filling', 'pastry', 5), ('Bake pie', 'pastry', 6), ('Slice & pack', 'packing', 1)],
    'Vanilla Bean Ice Cream Sundae': [('Assemble sundae', 'pastry', 2)],
}


def _enable_routings(env):
    user_group = env.ref('base.group_user')
    group = env.ref('mrp.group_mrp_routings', raise_if_not_found=False)
    if group and group not in user_group.implied_ids:
        user_group.sudo().write({'implied_ids': [Command.link(group.id)]})


def _workcenters(env):
    res = {}
    for seq, (slug, name, code, cost, eff, oee, setup, clean, color) in enumerate(WORKCENTERS, start=1):
        xid = f'rc_mrp_wc_{slug}'
        existing = _ref(env, xid) or env['mrp.workcenter'].sudo().search([('name', '=', name)], limit=1)
        if existing and not _ref(env, xid):
            _bind(env, xid, existing)
        res[slug] = existing or _get_or_create(env, xid, 'mrp.workcenter', {
            'name': name, 'code': code, 'costs_hour': cost, 'time_efficiency': eff, 'oee_target': oee,
            'time_start': setup, 'time_stop': clean, 'color': color, 'sequence': seq,
        })
    # the grill can take over sandwiches when the hot kitchen is overloaded, and vice versa
    if not res['grill'].alternative_workcenter_ids:
        res['grill'].alternative_workcenter_ids = [Command.set(res['hot_kitchen'].ids)]
        res['hot_kitchen'].alternative_workcenter_ids = [Command.set(res['grill'].ids)]
    return res


def _routings(env, wcs):
    boms = {}
    for bom in env['mrp.bom'].sudo().search([('type', '=', 'normal')]):
        name = bom.product_tmpl_id.name
        if name not in ROUTINGS or name in boms:
            continue
        boms[name] = bom
        if bom.operation_ids:
            continue
        bom.write({'operation_ids': [Command.create({
            'name': op, 'workcenter_id': wcs[slug].id, 'time_cycle_manual': minutes, 'time_mode': 'manual', 'sequence': seq * 10,
        }) for seq, (op, slug, minutes) in enumerate(ROUTINGS[name], start=1)]})
        # consume each component at the first operation that uses the station preparing it
        first_op = bom.operation_ids.sorted('sequence')[:1]
        bom.bom_line_ids.filtered(lambda l: not l.operation_id).write({'operation_id': first_op.id})
    return boms


# --------------------------------------------------------------------------- recipe instructions & ingredient steps
RECIPE_STEPS = {
    'Cheese Burger': {
        'Grill patties': [
            ('Grill Master Technique & Seasoning', 'instructions', 10,
             '<p><strong>Preparation & Grilling Protocol:</strong></p><ul><li>Pre-heat chrome flat grill to 205°C (400°F). Lightly oil cooking zone with clarified butter.</li><li>Place seasoned beef patties on grill without crowding.</li><li>Sear first side for 3.5 minutes until deep caramel crust develops. Flip once only.</li><li>Top with Aged Cheddar slice 1 minute before pulling; cover with melting cloche.</li></ul>',
             None, None, None, None),
            ('Minced Beef & Cheddar Ingredients', 'consumed_materials', 20,
             '<p>Verify batch lot and consume: 150g Minced Beef Patty, 1 slice Aged Cheddar Cheese, Salt & Pepper blend.</p>',
             None, None, None, None),
            ('Patty Core Temperature HACCP Check', 'measure', 30,
             '<p>Insert digital thermocouple probe into thickest part of patty center. Food safety minimum is 71°C.</p>',
             74.0, '°C', 71.0, 78.0),
        ],
        'Assemble burger': [
            ('Burger Architecture & Sauce Order', 'instructions', 10,
             '<p><strong>Layering Sequence (Bottom to Top):</strong></p><ol><li>Toasted brioche bun base</li><li>Smoked paprika house mayo (15g)</li><li>Crisp romaine lettuce & beef tomato slice</li><li>Grilled cheddar beef patty</li><li>Dill gherkins & thinly sliced red onion</li><li>Toasted sesame brioche lid brushed with herb butter</li></ol>',
             None, None, None, None),
            ('Brioche Buns & Fresh Produce', 'consumed_materials', 20,
             '<p>Verify and consume: Brioche Burger Bun, Romaine Lettuce, Roma Tomato, Pickles, Burger Sauce.</p>',
             None, None, None, None),
            ('Plating & Bun Glaze Inspection', 'picture', 30,
             '<p>Capture photo of assembled burger to check vertical stability, cheese drip, and golden bun glaze before packaging.</p>',
             None, None, None, None),
        ],
        'Box & label': [
            ('Thermal Hold & Packaging Standard', 'passfail', 10,
             '<p>Check box closure, steam vent opening, inclusion of branded napkins and wooden cutlery.</p>',
             None, None, None, None),
            ('Print Allergen & Nutritional Label', 'print_product_label', 20,
             '<p>Print barcode label with packaging timestamp and allergens: Gluten, Dairy, Mustard, Sesame.</p>',
             None, None, None, None),
            ('Register Finished Burger Yield', 'production', 30,
             '<p>Confirm completed burger count ready for pass dispatch to dine-in runners or takeaway counter.</p>',
             None, None, None, None),
        ],
    },
    'Bacon Burger': {
        'Grill patties & bacon': [
            ('Bacon & Beef Grilling Method', 'instructions', 10,
             '<p><strong>Grill Protocol:</strong></p><ul><li>Grill smoked bacon rashers until golden and crispy (approx. 2 mins per side). Drain on paper.</li><li>Sear beef patty at 205°C for 3.5 mins per side.</li><li>Melt sharp cheddar over patty and top with crisp bacon rashers.</li></ul>',
             None, None, None, None),
            ('Beef Patty & Smoked Bacon Batch', 'consumed_materials', 20,
             '<p>Record and consume Minced Beef (150g), Smoked Bacon rashers (2 strips), Cheddar slice.</p>',
             None, None, None, None),
            ('Internal Beef Temperature', 'measure', 30,
             '<p>Check core patty temperature with calibrated probe (min 71°C).</p>',
             74.0, '°C', 71.0, 78.0),
        ],
        'Assemble burger': [
            ('Bacon Burger Stacking Guide', 'instructions', 10,
             '<p>Toasted brioche, BBQ aioli, lettuce, tomato, cheesy bacon patty, caramelized onions, top bun.</p>',
             None, None, None, None),
            ('Finished Burger Photo Check', 'picture', 20,
             '<p>Take photo of finished bacon burger highlighting crispy bacon overhang and melted cheese.</p>',
             None, None, None, None),
        ],
        'Box & label': [
            ('Register Packaged Bacon Burgers', 'production', 10,
             '<p>Confirm boxed units ready for pickup.</p>',
             None, None, None, None),
        ],
    },
    'Pizza Margherita': {
        'Stretch dough & top': [
            ('Neapolitan Hand-Stretching Technique', 'instructions', 10,
             '<p><strong>Artisan Pizza Shaping:</strong></p><ul><li>Dust marble prep table with fine semolina flour. Hand-stretch 250g proofed dough ball from center outwards.</li><li>Preserve an elevated 1.5cm <em>cornicione</em> (outer crust rim) without flattening air pockets.</li><li>Spread 90g San Marzano tomato reduction in spiral motion from center outward.</li><li>Scatter 100g fresh Fior di Latte mozzarella cubes evenly.</li><li>Add 4 fresh sweet basil leaves and drizzle extra virgin olive oil.</li></ul>',
             None, None, None, None),
            ('Dough Ball & Fresh Cheese Consumption', 'consumed_materials', 20,
             '<p>Consume: 1x Pizza Dough Ball (250g), Fresh Mozzarella (100g), San Marzano Tomato Sauce (90g), Fresh Basil.</p>',
             None, None, None, None),
        ],
        'Bake in stone oven': [
            ('Stone Hearth Baking Protocol', 'instructions', 10,
             '<p>Slide pizza onto wooden peel. Launch directly onto stone deck. Bake for 3.5 to 4.5 minutes. Spin 180 degrees at minute 2 for even browning.</p>',
             None, None, None, None),
            ('Stone Oven Floor Temperature', 'measure', 20,
             '<p>Aim infrared pyrometer at center of stone floor. Target temperature is 350°C.</p>',
             350.0, '°C', 330.0, 380.0),
            ('Leopard-Crust & Melt Inspection', 'passfail', 30,
             '<p>Inspect crust blister (leopard spotting), fully melted creamy mozzarella, and non-soggy center base.</p>',
             None, None, None, None),
        ],
        'Cut & box': [
            ('Slicing & Visual Quality Photo', 'picture', 10,
             '<p>Slice cleanly into 8 triangular wedges using rocker blade. Take photo inside pizza takeaway box.</p>',
             None, None, None, None),
            ('Register Finished Pizza Output', 'production', 20,
             '<p>Confirm finished pizza quantity ready for restaurant pass / delivery.</p>',
             None, None, None, None),
        ],
    },
    'Pizza Vegetarian': {
        'Stretch dough & top': [
            ('Vegetable Medley Topping Protocol', 'instructions', 10,
             '<p>Stretch dough, apply tomato sauce, mozzarella, sliced button mushrooms, bell pepper strips, cherry tomatoes, and red onion rings.</p>',
             None, None, None, None),
            ('Fresh Vegetables & Cheese Batch', 'consumed_materials', 20,
             '<p>Record Pizza Dough (250g), Mozzarella (100g), Tomato Sauce (90g), Mushrooms (40g), Tomatoes (30g), Bell Peppers (30g).</p>',
             None, None, None, None),
        ],
        'Bake in stone oven': [
            ('Stone Oven Deck Temperature', 'measure', 10,
             '<p>Check baking floor temperature before loading pizza.</p>',
             350.0, '°C', 330.0, 380.0),
            ('Vegetable Roast & Crispiness Check', 'passfail', 20,
             '<p>Verify mushrooms are tender, peppers roasted, and crust is golden crisp.</p>',
             None, None, None, None),
        ],
        'Cut & box': [
            ('Vegetarian Pizza Presentation Check', 'picture', 10,
             '<p>Photo verification of colorful fresh vegetable coverage and uniform slices.</p>',
             None, None, None, None),
            ('Register Finished Vegetarian Pizzas', 'production', 20,
             '<p>Confirm completed pizza count.</p>',
             None, None, None, None),
        ],
    },
    'Pasta Bolognese': {
        'Cook pasta & ragu': [
            ('Recipe & Prep Instructions', 'instructions', 10,
             '<p>Boil water with salt, simmer ragu slowly for 25 minutes. Toss al dente spaghetti directly in sauce with butter.</p>',
             None, None, None, None),
            ('Pasta Batch Ingredients', 'consumed_materials', 20,
             '<p>Scan pasta and tomato paste lots. Record Spaghetti (160g), Minced Beef (120g), Tomato Sauce (150g), Butter (20g).</p>',
             None, None, None, None),
            ('Plating & Presentation Check', 'picture', 30,
             '<p>Take a picture of the finished pasta bowl before dispatch.</p>',
             None, None, None, None),
            ('Register Cooked Portions', 'production', 40,
             '<p>Confirm final cooked quantity.</p>',
             None, None, None, None),
        ],
        'Portion & pack': [
            ('Portion Packaging Standard', 'passfail', 10,
             '<p>Check bowl seal, parmesan packet, and napkin placement.</p>',
             None, None, None, None),
        ],
    },
    'Pasta 4 Formaggi': {
        'Cook pasta & cheese sauce': [
            ('Four-Cheese Emulsion Method', 'instructions', 10,
             '<p><strong>Cooking Protocol:</strong></p><ul><li>Boil spaghetti for 7 minutes in salted water (10g salt/L).</li><li>In wide saute pan, reduce heavy cream with Gorgonzola, Fontina, and Taleggio over low heat.</li><li>Toss pasta directly in cheese cream with 20g butter and fresh ground nutmeg.</li><li>Finish with freshly grated Parmigiano Reggiano off heat to prevent stringiness.</li></ul>',
             None, None, None, None),
            ('Artisan Cheeses & Cream Consumption', 'consumed_materials', 20,
             '<p>Consume: Spaghetti (160g), Four-Cheese Mix (140g), Heavy Dairy Cream (80g), Butter (20g).</p>',
             None, None, None, None),
            ('Cheese Sauce Temperature Check', 'measure', 30,
             '<p>Sauce serving temperature check (target 80°C).</p>',
             80.0, '°C', 76.0, 85.0),
        ],
        'Portion & pack': [
            ('Pasta Swirl Plating Photo', 'picture', 10,
             '<p>Twirl pasta with carving fork into deep warm bowl. Take photo of velvet sauce coating and microgreens garnish.</p>',
             None, None, None, None),
            ('Register Finished Pasta Portions', 'production', 20,
             '<p>Confirm completed portions count.</p>',
             None, None, None, None),
        ],
    },
    'Club Sandwich': {
        'Prepare fillings': [
            ('Roast Chicken & Bacon Prep', 'instructions', 10,
             '<p>Thinly slice roast chicken breast. Crisp smoked bacon. Mix mayonnaise with Dijon mustard. Wash romaine leaves.</p>',
             None, None, None, None),
            ('Proteins & Fresh Ingredients Batch', 'consumed_materials', 20,
             '<p>Record Chicken Breast (120g), Bacon (40g), Romaine Lettuce (40g), Sliced Tomato (50g), Cheddar (1 slice).</p>',
             None, None, None, None),
        ],
        'Assemble & toast': [
            ('Triple-Decker Assembly Guide', 'instructions', 10,
             '<p>Toast 3 slices of sourdough bread. Bottom: mayo, chicken, tomato. Middle toast: mayo, bacon, lettuce, cheddar. Top toast. Cut into triangles with bamboo skewers.</p>',
             None, None, None, None),
            ('Sandwich Cross-Section Presentation', 'picture', 20,
             '<p>Take photo of cut triangles showing distinct neat layers.</p>',
             None, None, None, None),
        ],
        'Wrap & label': [
            ('Register Finished Club Sandwiches', 'production', 10,
             '<p>Confirm packed sandwich units.</p>',
             None, None, None, None),
        ],
    },
    'Spicy Tuna Sandwich': {
        'Prepare tuna mix': [
            ('Spicy Tuna Spread Formulation', 'instructions', 10,
             '<p>Drain tuna flakes. Fold with Japanese Kewpie mayo, sriracha chili paste, finely diced spring onions and celery.</p>',
             None, None, None, None),
            ('Tuna & Seasonings Consumption', 'consumed_materials', 20,
             '<p>Record Tuna (110g), Mayo & Sriracha (30g), Bread (2 slices), Lettuce & Tomato.</p>',
             None, None, None, None),
        ],
        'Assemble & toast': [
            ('Panini Pressing & Toasting', 'instructions', 10,
             '<p>Press on ribbed panini grill for 2.5 minutes until golden and cheese begins to melt.</p>',
             None, None, None, None),
            ('Panini Grill Temperature', 'measure', 20,
             '<p>Check panini press surface temperature.</p>',
             190.0, '°C', 180.0, 205.0),
        ],
        'Wrap & label': [
            ('Register Packaged Tuna Sandwiches', 'production', 10,
             '<p>Confirm completed sandwich units.</p>',
             None, None, None, None),
        ],
    },
    'Lunch Maki 18pc': {
        'Cook & season sushi rice': [
            ('Sushi Shari Rice Perfection', 'instructions', 10,
             '<p><strong>Authentic Shari Protocol:</strong></p><ul><li>Rinse short-grain sushi rice until water is crystal clear.</li><li>Cook in sushi steamer with kombu seaweed.</li><li>Turn out into wooden hangiri bowl. Gently cut in seasoned sushi vinegar (sushi-su) with shamoji paddle.</li><li>Cool to body temperature (36°C) using hand fan for signature glossy pearl shine.</li></ul>',
             None, None, None, None),
            ('Sushi Rice & Seasoning Batch', 'consumed_materials', 20,
             '<p>Record: Sushi Rice (280g), Nori Seaweed (3 sheets), Sushi Vinegar (40ml).</p>',
             None, None, None, None),
            ('Shari Rice Rolling Temperature', 'measure', 30,
             '<p>Ensure rice is at body temperature before rolling (optimal 36°C).</p>',
             36.0, '°C', 34.0, 38.0),
        ],
        'Roll & cut maki': [
            ('Rolling & Yanagiba Knife Slicing', 'instructions', 10,
             '<p>Lay nori on makisu mat. Spread 90g rice evenly leaving 1cm top margin. Add salmon and avocado. Roll into firm cylindrical roll. Slice into 6 uniform rounds using moist yanagiba knife.</p>',
             None, None, None, None),
            ('Sashimi Salmon & Hass Avocado Batch', 'consumed_materials', 20,
             '<p>Consume: Sashimi Grade Fresh Salmon (140g), Hass Avocado (0.5 pc).</p>',
             None, None, None, None),
            ('Sushi Bento Platter Photo', 'picture', 30,
             '<p>Take photo of 18-piece sushi box with wasabi rose, pickled ginger, and soy dipping cups.</p>',
             None, None, None, None),
            ('Freshness & Hygiene Inspection', 'passfail', 40,
             '<p>Check cold-chain temperature under 4°C, fresh ocean aroma, and pristine clean cuts.</p>',
             None, None, None, None),
        ],
        'Box & label': [
            ('Register Completed Sushi Boxes', 'production', 10,
             '<p>Confirm completed 18pc maki boxes for sushi takeaway and delivery.</p>',
             None, None, None, None),
        ],
    },
    'Salmon and Avocado': {
        'Cook & season sushi rice': [
            ('Sushi Shari Preparation', 'instructions', 10,
             '<p>Steam rice, dress with seasoned rice vinegar, cool to 36°C.</p>',
             None, None, None, None),
            ('Sushi Rice Temperature', 'measure', 20,
             '<p>Check rice temperature.</p>',
             36.0, '°C', 34.0, 38.0),
        ],
        'Roll & cut': [
            ('Roll & Slicing Instructions', 'instructions', 10,
             '<p>Roll salmon and ripe avocado tightly in toasted nori seaweed. Slice into 8 pieces.</p>',
             None, None, None, None),
            ('Fresh Salmon & Avocado Ingredients', 'consumed_materials', 20,
             '<p>Consume Salmon (160g), Avocado (1 pc), Nori (2 sheets), Rice (180g).</p>',
             None, None, None, None),
            ('Roll Cross-Section Inspection Photo', 'picture', 30,
             '<p>Verify vibrant salmon orange against emerald avocado and pearl rice.</p>',
             None, None, None, None),
        ],
        'Box & label': [
            ('Register Finished Salmon & Avocado Rolls', 'production', 10,
             '<p>Confirm finished roll portions.</p>',
             None, None, None, None),
        ],
    },
    'Espresso': {
        'Grind & pull shot': [
            ('Barista Specialty Extraction Standards', 'instructions', 10,
             '<p><strong>Espresso Pull Protocol:</strong></p><ul><li>Grind 18.5g of freshly roasted single-origin Arabica beans into portafilter.</li><li>Level coffee grounds with distribution tool; tamp firmly with 15kg pressure.</li><li>Flush group head for 2 seconds to stabilize brew water temperature.</li><li>Engage portafilter and extract immediately. Target yield: 36g liquid in 28 seconds.</li><li>Crema must be thick hazelnut with persistent tiger striping.</li></ul>',
             None, None, None, None),
            ('Coffee Beans & Takeaway Cup Batch', 'consumed_materials', 20,
             '<p>Consume Specialty Coffee Beans (18.5g), Takeaway Paper Cup & Lid.</p>',
             None, None, None, None),
            ('Brew Ratio & Yield Measurement', 'measure', 30,
             '<p>Weigh espresso liquid yield on precision barista scale (target 36g for double shot).</p>',
             36.0, 'g', 34.0, 38.0),
            ('Sensory Crema & Aroma Evaluation', 'passfail', 40,
             '<p>Check thick persistent crema, rich floral/chocolate aroma, zero bitter astringency.</p>',
             None, None, None, None),
            ('Register Pulled Espresso', 'production', 50,
             '<p>Confirm beverage completed for barista counter.</p>',
             None, None, None, None),
        ],
    },
    'Green Tea': {
        'Steep tea': [
            ('Artisan Tea Steeping Protocol', 'instructions', 10,
             '<p>Heat filtered spring water to 80°C (never boiling). Measure 3g whole leaf green tea. Steep for exactly 2.5 minutes.</p>',
             None, None, None, None),
            ('Steeping Water Temperature', 'measure', 20,
             '<p>Check water temperature before pouring over green tea leaves.</p>',
             80.0, '°C', 76.0, 84.0),
            ('Tea Leaves & Cup Consumption', 'consumed_materials', 30,
             '<p>Record Green Tea Leaves (10g) and Paper Cup.</p>',
             None, None, None, None),
            ('Register Steeped Tea', 'production', 40,
             '<p>Confirm beverage completed.</p>',
             None, None, None, None),
        ],
    },
    'Milkshake Banana': {
        'Blend milkshake': [
            ('Milkshake Formulation & Aeration', 'instructions', 10,
             '<p>Add 2 ripe bananas, 220ml cold whole milk, 100g vanilla gelato, and 15ml vanilla syrup. Blend on high for 45 seconds until velvety thick.</p>',
             None, None, None, None),
            ('Gelato & Fresh Fruit Ingredients', 'consumed_materials', 20,
             '<p>Consume Bananas (150g), Milk (220ml), Vanilla Gelato (100g).</p>',
             None, None, None, None),
            ('Serving Temperature Check', 'measure', 30,
             '<p>Check serving chill temperature (target -2°C).</p>',
             -2.0, '°C', -4.0, 0.0),
        ],
        'Cap & label': [
            ('Whipped Cream & Garnish Photo', 'picture', 10,
             '<p>Top with whipped cream dome, banana chip, and caramel drizzle. Photo check.</p>',
             None, None, None, None),
            ('Register Finished Milkshake', 'production', 20,
             '<p>Confirm beverage ready for service.</p>',
             None, None, None, None),
        ],
    },
    'Tiramisu': {
        'Whip mascarpone cream': [
            ('Zabaglione & Mascarpone Cream Technique', 'instructions', 10,
             '<p><strong>Crema Tradizionale:</strong></p><ul><li>Whisk egg yolks with sugar over bain-marie until pale, thick ribbon stage (zabaglione).</li><li>Gently fold room-temperature Italian mascarpone until silky smooth.</li><li>Whip heavy cream to soft peaks; fold into mascarpone in 3 batches preserving volume.</li></ul>',
             None, None, None, None),
            ('Dairy & Egg Ingredients Batch', 'consumed_materials', 20,
             '<p>Record Mascarpone (100g), Heavy Cream (60g), Fresh Eggs (1 pc), Sugar (30g).</p>',
             None, None, None, None),
        ],
        'Layer & set': [
            ('Savoiardi Espresso Soak & Layering', 'instructions', 10,
             '<p>Dip ladyfingers for 1.5 seconds into chilled espresso with Marsala wine essence. Lay first biscuit tier. Spread cream. Repeat second tier. Chill at 2°C for 6 hours minimum.</p>',
             None, None, None, None),
            ('Cocoa Dusting & Finishing Photo', 'picture', 20,
             '<p>Dust with Valrhona 100% Dutch cocoa powder through fine mesh. Photograph dessert tray.</p>',
             None, None, None, None),
        ],
        'Portion & pack': [
            ('Dessert Slice Portion Weight', 'measure', 10,
             '<p>Weigh individual slice on pastry scale (target 180g).</p>',
             180.0, 'g', 170.0, 195.0),
            ('Register Finished Tiramisu Slices', 'production', 20,
             '<p>Confirm completed dessert portions for pastry display.</p>',
             None, None, None, None),
        ],
    },
    'New York Cheesecake': {
        'Mix & bake cheesecake': [
            ('Graham Crust & Smooth Cream Cheese Batter', 'instructions', 10,
             '<p>Blend cream cheese, vanilla bean paste, eggs, and sour cream on low speed to avoid air bubbles. Pour over pressed graham biscuit butter crust.</p>',
             None, None, None, None),
            ('Cream Cheese & Dairy Consumption', 'consumed_materials', 20,
             '<p>Consume Cream Cheese (140g), Heavy Cream (60g), Eggs (1 pc), Sugar (40g), Butter (30g).</p>',
             None, None, None, None),
            ('Water Bath Baking Temperature', 'measure', 30,
             '<p>Bake in water bath at 160°C for 55 minutes until edges are set and center gently jiggles.</p>',
             160.0, '°C', 155.0, 165.0),
        ],
        'Chill & portion': [
            ('Chilled Texture & Clean Cut Inspection', 'passfail', 10,
             '<p>Refrigerate 8 hours. Slice with hot knife wiped clean after every cut.</p>',
             None, None, None, None),
            ('Cheesecake Slice Photo', 'picture', 20,
             '<p>Take photo of slice showing velvet dense crumb and golden crust base.</p>',
             None, None, None, None),
        ],
        'Pack': [
            ('Register Packaged Cheesecake Slices', 'production', 10,
             '<p>Confirm finished portions.</p>',
             None, None, None, None),
        ],
    },
    'Chocolate Lava Cake': {
        'Mix batter & fill moulds': [
            ('Molten Lava Batter Formulation', 'instructions', 10,
             '<p><strong>Fondant Master Technique:</strong></p><ul><li>Melt 70% dark Belgian chocolate with French unsalted butter over hot water bath at 48°C.</li><li>Beat whole eggs and yolks with caster sugar until pale and tripled in volume.</li><li>Fold warm chocolate mixture into eggs; sift in flour gently in two batches.</li><li>Brush ramekins with softened butter; dust with cocoa powder. Fill moulds to 80%.</li></ul>',
             None, None, None, None),
            ('Belgian Chocolate & French Butter Batch', 'consumed_materials', 20,
             '<p>Consume Dark Chocolate (90g), Butter (60g), Eggs (2 pcs), Flour (40g), Sugar (40g).</p>',
             None, None, None, None),
        ],
        'Bake': [
            ('Oven Bake Temperature & Time', 'measure', 10,
             '<p>Bake at 195°C for exactly 11 minutes so outer cake sets while core stays liquid ganache.</p>',
             195.0, '°C', 190.0, 200.0),
            ('Molten Center Quality Test', 'passfail', 20,
             '<p>Ensure cake has domed edges with a soft, trembling center.</p>',
             None, None, None, None),
        ],
        'Pack': [
            ('Plating Photo with Raspberry Garnish', 'picture', 10,
             '<p>Dust with icing sugar, garnish with fresh mint and raspberry. Photo check.</p>',
             None, None, None, None),
            ('Register Finished Lava Cakes', 'production', 20,
             '<p>Confirm cakes ready for dining service or takeaway heating instructions.</p>',
             None, None, None, None),
        ],
    },
    'Warm Apple Pie': {
        'Make pastry & filling': [
            ('Flaky Shortcrust & Spiced Apple Filling', 'instructions', 10,
             '<p>Toss sliced Granny Smith apples with brown sugar, Ceylon cinnamon, nutmeg, and lemon juice. Roll cold butter pastry to 3mm thickness.</p>',
             None, None, None, None),
            ('Fresh Apples & Pastry Ingredients', 'consumed_materials', 20,
             '<p>Consume Apples (180g), Flour (80g), Butter (50g), Sugar (40g).</p>',
             None, None, None, None),
        ],
        'Bake pie': [
            ('Convection Pie Baking Temperature', 'measure', 10,
             '<p>Bake at 185°C for 40 minutes until pastry is deep golden and apple juices bubble through lattice slits.</p>',
             185.0, '°C', 180.0, 190.0),
        ],
        'Slice & pack': [
            ('Pie Golden Crust Photo', 'picture', 10,
             '<p>Photo of sliced pie wedge showing caramelized apples and crisp layers.</p>',
             None, None, None, None),
            ('Register Finished Pie Slices', 'production', 20,
             '<p>Confirm completed portions.</p>',
             None, None, None, None),
        ],
    },
    'Vanilla Bean Ice Cream Sundae': {
        'Assemble sundae': [
            ('Sundae Layering & Hot Fudge Technique', 'instructions', 10,
             '<p>Scoop 3 spheres of Madagascar vanilla gelato into chilled sundae goblet. Drizzle warm Belgian dark chocolate fudge. Pipe fresh vanilla bean chantilly cream. Crown with Maraschino cherry.</p>',
             None, None, None, None),
            ('Gelato & Fudge Ingredients Batch', 'consumed_materials', 20,
             '<p>Record Vanilla Ice Cream (180g), Heavy Cream (40g), Dark Chocolate Fudge (30g).</p>',
             None, None, None, None),
            ('Sundae Presentation Photo', 'picture', 30,
             '<p>Take photo of towering sundae presentation with fudge drizzle and cherry on top.</p>',
             None, None, None, None),
            ('Register Finished Sundaes', 'production', 40,
             '<p>Confirm completed sundae count.</p>',
             None, None, None, None),
        ],
    },
}


def _create_recipe_instructions(env, boms):
    if 'mrp.routing.workcenter.step' not in env:
        return
    Step = env['mrp.routing.workcenter.step'].sudo()
    for bom in env['mrp.bom'].sudo().search([('type', '=', 'normal')]):
        prod_name = bom.product_tmpl_id.name
        if prod_name not in RECIPE_STEPS:
            continue
        op_dict = RECIPE_STEPS[prod_name]
        for op in bom.operation_ids:
            if op.name not in op_dict:
                continue
            steps_data = op_dict[op.name]
            for title, t_type, seq, instructions, norm, unit, t_min, t_max in steps_data:
                existing = Step.search([('workorder_operation_id', '=', op.id), ('title', '=', title)], limit=1)
                if existing:
                    continue
                vals = {
                    'title': title,
                    'test_type': t_type,
                    'sequence': seq,
                    'workorder_operation_id': op.id,
                    'instructions': instructions,
                }
                if norm is not None:
                    vals['norm'] = norm
                    vals['norm_unit'] = unit or 'mm'
                    vals['tolerance_min'] = t_min
                    vals['tolerance_max'] = t_max
                Step.create(vals)


# --------------------------------------------------------------------------- manufacturing orders
# xid, product, qty, state, start offset in days (negative = past), origin, operator(s)
ORDERS = [
    ('rc_mrp_mo_tiramisu_done', 'Tiramisu', 30, 'done', -27, 'Weekend dessert counter', ['Ananya Sharma']),
    ('rc_mrp_mo_burger_done', 'Cheese Burger', 40, 'done', -21, 'BlueWave team lunch', ['Vishnu Kumar']),
    ('rc_mrp_mo_pizza_done', 'Pizza Margherita', 25, 'done', -14, 'Film Society screening night', ['Vishnu Kumar', 'Rahul Nair']),
    ('rc_mrp_mo_lava_done', 'Chocolate Lava Cake', 24, 'done', -7, 'POS restock - desserts', ['Ananya Sharma']),
    ('rc_mrp_mo_maki_done', 'Lunch Maki 18pc', 15, 'done', -3, 'Nest Coworking lunch boxes', ['Rahul Nair']),
    ('rc_mrp_mo_club_to_close', 'Club Sandwich', 30, 'to_close', -1, 'Harbour Point meeting platters', ['Vishnu Kumar']),
    ('rc_mrp_mo_bolognese_progress', 'Pasta Bolognese', 20, 'progress', 0, 'Corporate lunch run', ['Vishnu Kumar']),
    ('rc_mrp_mo_cheesecake_progress', 'New York Cheesecake', 16, 'progress', 0, 'POS restock - desserts', ['Ananya Sharma']),
    ('rc_mrp_mo_veg_pizza_paused', 'Pizza Vegetarian', 20, 'paused', 0, 'Evening takeaway prep', ['Rahul Nair']),
    ('rc_mrp_mo_bacon_ready', 'Bacon Burger', 35, 'confirmed', 1, 'Coastal Runners post-race meal', []),
    ('rc_mrp_mo_apple_pie_ready', 'Warm Apple Pie', 24, 'confirmed', 2, 'Weekend dessert counter', []),
    ('rc_mrp_mo_salmon_waiting', 'Salmon and Avocado', 40, 'waiting', 3, 'Marina Bay wedding canapes', []),
    ('rc_mrp_mo_milkshake_draft', 'Milkshake Banana', 50, 'draft', 5, "St. Teresa's annual day", []),
    ('rc_mrp_mo_green_tea_cancel', 'Green Tea', 30, 'cancel', -10, 'Yoga studio event (cancelled)', []),
]


def _top_up_components(env, mo, factor=1.5):
    """Make sure the MO's components are in stock (the kitchen received its morning delivery)."""
    location = mo.location_src_id
    Quant = env['stock.quant'].sudo()
    for move in mo.move_raw_ids:
        product = move.product_id
        if not product.is_storable or preexisting(product):
            continue  # never change the stock of products that existed before this install run
        need = move.product_uom_qty * factor
        available = product.with_context(location=location.id).qty_available
        if available < need:
            Quant._update_available_quantity(product, location, need - available)


def _log_time(env, wo, start, minutes, employee, closed=True):
    vals = wo._prepare_timeline_vals(minutes, start, start + timedelta(minutes=minutes) if closed else False,
                                     employee_id=employee.id if employee else None)
    vals['user_id'] = env.ref('base.user_admin').id
    if employee:
        vals['employee_id'] = employee.id
    return env['mrp.workcenter.productivity'].sudo().create(vals)


def _create_mo(env, spec, boms):
    xid, product_name, qty, state, offset, origin, operators = spec
    if _ref(env, xid):
        return
    bom = boms.get(product_name)
    if not bom:
        return
    product = bom.product_tmpl_id.product_variant_ids[:1]
    start = (_now() + timedelta(days=offset)).replace(hour=7 if offset <= 0 else 8, minute=0)
    employees = [e for e in (_employee(env, n) for n in operators) if e]
    mo = env['mrp.production'].sudo().create({
        'product_id': product.id, 'bom_id': bom.id, 'product_qty': qty, 'origin': origin,
        'date_start': start, 'user_id': env.ref('base.user_admin').id,
        'priority': '1' if state in ('progress', 'waiting') else '0',
    })
    _bind(env, xid, mo)
    if state == 'draft':
        return
    if state != 'waiting':
        _top_up_components(env, mo)
    mo.action_confirm()
    if state == 'cancel':
        mo.action_cancel()
        return
    mo.action_assign()
    if state in ('confirmed', 'waiting'):
        return

    workorders = mo.workorder_ids.sorted('sequence')
    emp = employees[0] if employees else False
    if state in ('done', 'to_close'):
        mo.qty_producing = qty
        mo.set_qty_producing()
        cursor = start
        for i, wo in enumerate(workorders):
            operator = employees[i % len(employees)] if employees else False
            minutes = max(5, round(wo.duration_expected * (0.9 + 0.05 * i)))
            _log_time(env, wo, cursor, minutes, operator)
            wo.button_finish()
            wo.write({'date_start': cursor, 'date_finished': cursor + timedelta(minutes=minutes)})
            cursor += timedelta(minutes=minutes + 5)
        if state == 'done':
            mo.with_context(skip_consumption=True, skip_backorder=True).button_mark_done()
            mo.with_context(force_date=True).write({'date_start': start, 'date_finished': cursor})
            (mo.move_raw_ids | mo.move_finished_ids).filtered(lambda m: m.state == 'done').write({'date': cursor})
            (mo.move_raw_ids | mo.move_finished_ids).move_line_ids.write({'date': cursor})
        return

    # in progress / paused: first operation done earlier this morning, the next one is running
    first, rest = workorders[:1], workorders[1:]
    if rest:
        mo.qty_producing = qty
        mo.set_qty_producing()
        minutes = max(5, round(first.duration_expected))
        _log_time(env, first, start, minutes, emp)
        first.button_finish()
        first.write({'date_start': start, 'date_finished': start + timedelta(minutes=minutes)})
        current = rest[:1]
    else:
        current = first
    if state == 'progress':
        current.with_context(sf_employee_id=emp.id if emp else False).button_start()
        running = current.time_ids.filtered(lambda t: not t.date_end)
        running.write({'date_start': _now() - timedelta(minutes=25), 'employee_id': emp.id if emp else False,
                       'user_id': env.ref('base.user_admin').id})
    else:  # paused: operator logged 20 minutes then stopped for a break
        current.button_start()
        current.time_ids.filtered(lambda t: not t.date_end)._close()
        current.time_ids.write({'date_start': _now() - timedelta(minutes=60), 'date_end': _now() - timedelta(minutes=40),
                                'employee_id': emp.id if emp else False, 'user_id': env.ref('base.user_admin').id})


def _downtime(env, wcs):
    if _ref(env, 'rc_mrp_loss_pizza_oven'):
        return
    loss = env['mrp.workcenter.productivity.loss'].sudo().search([('loss_type', '=', 'availability'), ('name', 'ilike', 'Equipment')], limit=1)
    if not loss:
        return
    start = (_now() - timedelta(days=6)).replace(hour=11, minute=10)
    line = env['mrp.workcenter.productivity'].sudo().create({
        'workcenter_id': wcs['pizza_oven'].id, 'loss_id': loss.id, 'user_id': env.ref('base.user_admin').id,
        'description': 'Stone oven burner ignition failure - technician called',
        'date_start': start, 'date_end': start + timedelta(minutes=45),
    })
    _bind(env, 'rc_mrp_loss_pizza_oven', line)


# --------------------------------------------------------------------------- entry point
def load_mrp_suite_demo_data(env):
    if 'mrp.production' not in env:
        _logger.info("Hudson POS: Manufacturing not installed, skipping MRP demo data.")
        return
    ctx = {}
    for name, step in (
        ('routings group', lambda: _enable_routings(env)),
        ('work centers', lambda: ctx.update(wcs=_workcenters(env))),
        ('operations', lambda: ctx.update(boms=_routings(env, ctx['wcs']))),
        ('recipe instructions', lambda: _create_recipe_instructions(env, ctx.get('boms', {}))),
        ('downtime', lambda: _downtime(env, ctx['wcs'])),
    ):
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: MRP demo step '%s' failed: %s", name, e)
            if name in ('work centers', 'operations'):
                return
    for spec in ORDERS:
        try:
            with env.cr.savepoint():
                _create_mo(env, spec, ctx['boms'])
        except Exception as e:
            _logger.exception("Hudson POS: MRP demo order %s failed: %s", spec[0], e)
    _logger.info("Hudson POS: Resto Cafe Manufacturing & Shop Floor demo data loaded.")
