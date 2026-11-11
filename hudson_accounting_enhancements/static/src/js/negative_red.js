/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

/**
 * Hudson Accounting Enhancements - Negative Value Coloring
 * 
 * Applies red color to negative monetary/numeric values in the backend UI.
 * Uses a MutationObserver to catch dynamically rendered list/pivot views.
 */

function applyNegativeColoring() {
    // Target all relevant cells - list view monetary cells, pivot cells, form monetary fields
    const selectors = [
        ".o_list_number",           // list view numeric/monetary td cells
        ".o_field_monetary",        // form view monetary fields
        ".o_field_float",           // form view float fields
        ".o_pivot_cell_value",      // pivot view cells
        ".table-reports td.text-end", // custom accounting report cells
    ].join(", ");

    const elements = document.querySelectorAll(selectors);
    elements.forEach((el) => {
        const text = (el.textContent || "").trim();
        // Match negative numbers: starts with - or has - followed by digits
        // Exclude hyphens in names/dates (require digit after -)
        const isNegative = /^\s*[-−]\s*[\d]/.test(text) || /[₹$€£¥]\s*[-−]/.test(text) || text.startsWith("-");

        if (isNegative) {
            el.style.setProperty("color", "#dc3545", "important");
        } else {
            // Only remove our color if we set it (don't disturb other styles)
            if (el.style.color === "rgb(220, 53, 69)") {
                el.style.removeProperty("color");
            }
        }
    });
}

// Service that registers a MutationObserver when the webclient starts
const negativeColorService = {
    dependencies: [],
    start() {
        // Run once immediately after a short delay to catch initial render
        setTimeout(applyNegativeColoring, 500);
        setTimeout(applyNegativeColoring, 1500);

        // Watch for DOM changes (Odoo re-renders views dynamically)
        const observer = new MutationObserver((mutations) => {
            // Only process if something was actually added to the DOM
            const hasNewNodes = mutations.some(m => m.addedNodes.length > 0);
            if (hasNewNodes) {
                // Debounce slightly to avoid running on every micro-mutation
                clearTimeout(negativeColorService._debounce);
                negativeColorService._debounce = setTimeout(applyNegativeColoring, 100);
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
        });

        return {};
    },
    _debounce: null,
};

registry.category("services").add("hudson_negative_color", negativeColorService);
