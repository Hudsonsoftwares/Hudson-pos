/** @odoo-module **/

import * as owl from "@odoo/owl";

if (owl && !owl.useState && owl.proxy) {
    owl.useState = owl.proxy;
}
