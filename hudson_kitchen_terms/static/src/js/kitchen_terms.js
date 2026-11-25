/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { LazyTranslatedString } from "@web/core/l10n/translation";
import { session } from "@web/session";

/**
 * Kitchen terminology for client-side (_t) strings.
 *
 * A string is only renamed when BOTH conditions hold:
 *  1. it comes from a Manufacturing module (`this.context` is the technical
 *     module name injected by the JS transpiler, e.g. "mrp", "mrp_workorder");
 *  2. the user is currently inside the Manufacturing app.
 * Strings of Payroll, HR, Accounting, etc. are never touched.
 */
const KITCHEN_EXTRA_MODULES = ["hudson_shopfloor"];

function isKitchenModule(moduleName) {
    return (
        typeof moduleName === "string" &&
        (moduleName === "mrp" ||
            moduleName.startsWith("mrp_") ||
            KITCHEN_EXTRA_MODULES.includes(moduleName))
    );
}

let regexList = [];

/**
 * (Re)build the replacement list. Called at load time and again after a
 * Kitchen Label is saved, so changes apply without a full page reload.
 * @param {Record<string, string>} terms
 */
export function setKitchenTerms(terms) {
    const sortedKeys = Object.keys(terms || {}).sort((a, b) => b.length - a.length);
    regexList = sortedKeys.map((key) => {
        const left = /^[a-zA-Z0-9]/.test(key) ? "\\b" : "(?:^|\\s)";
        const right = /[a-zA-Z0-9]$/.test(key) ? "\\b" : "(?:$|\\s)";
        const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        return {
            regex: new RegExp(`${left}${escaped}${right}`, "gi"),
            replacement: terms[key],
        };
    });
}

function applyKitchenTerms(str) {
    let result = str;
    for (const { regex, replacement } of regexList) {
        result = result.replace(regex, (match) => {
            const core = match.trim();
            const lead = match.slice(0, match.indexOf(core));
            const trail = match.slice(match.indexOf(core) + core.length);
            let out = replacement;
            if (core.length > 1 && core === core.toUpperCase() && replacement !== replacement.toUpperCase()) {
                out = replacement.toUpperCase();
            } else if (core === core.toLowerCase()) {
                out = replacement.toLowerCase();
            }
            return lead + out + trail;
        });
    }
    return result;
}

if (session && session.kitchen_mode && session.kitchen_terms && (session.kitchen_mrp_app_ids?.length || session.kitchen_mrp_app_id)) {
    setKitchenTerms(session.kitchen_terms);
    const mrpAppIds = (session.kitchen_mrp_app_ids || (session.kitchen_mrp_app_id ? [session.kitchen_mrp_app_id] : [])).map(String);

    function isManufacturingAppActive() {
        try {
            // Set by the menu service each time the current app changes.
            return mrpAppIds.includes(String(sessionStorage.getItem("menu_id")));
        } catch {
            return false;
        }
    }

    patch(LazyTranslatedString.prototype, {
        translate() {
            const res = super.translate(...arguments);
            if (
                regexList.length &&
                typeof res === "string" &&
                res &&
                isKitchenModule(this.context) &&
                isManufacturingAppActive()
            ) {
                return applyKitchenTerms(res);
            }
            return res;
        },
    });
}
