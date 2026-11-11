/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { FloatField } from "@web/views/fields/float/float_field";
import { MonetaryField } from "@web/views/fields/monetary/monetary_field";
import { ProgressBarField } from "@web/views/fields/progress_bar/progress_bar_field";
import { parseFloat } from "@web/views/fields/parsers";

/**
 * Sanitizes a number string containing commas before it is parsed by Odoo's parseFloat/parseNumber.
 *
 * In environments where comma is a thousands separator (e.g. India, US, UK, UAE, etc.),
 * entering values with comma separation like "25,000", "5,000", "30,000", or "1,00,000"
 * would previously be erroneously parsed by Odoo as decimal fractions (e.g. 25.00, 5.00, 30.00).
 *
 * This sanitizer ensures:
 * 1. Values with both commas and dots (e.g. "25,000.50" or "1,00,000.00"):
 *    - Comma is stripped as thousands separator, dot preserved as decimal point.
 * 2. Values with commas and no dot:
 *    - Multiple commas (e.g. "1,00,000" or "10,00,000"): All commas stripped.
 *    - Single comma followed by 3 digits (e.g. "25,000", "5,000", "30,000", "1,500"):
 *      Treated as thousands separator, comma stripped -> 25000, 5000, 30000, 1500.
 *    - Single comma followed by 1 or 2 digits (e.g. "25,5", "25,50") with no dot:
 *      Treated as decimal comma for European numpad compatibility -> converted to dot.
 * 3. Mathematical expressions starting with '=' (e.g. "=25,000 + 5,000"):
 *    - Tokens are sanitized individually so formulas evaluate accurately.
 */
export function sanitizeNumberComma(val) {
    if (typeof val !== "string") {
        return val;
    }
    const s = val.trim();
    if (!s) {
        return val;
    }

    if (s.startsWith("=")) {
        return (
            "=" +
            s
                .slice(1)
                .split(/([-+*/()^])/)
                .map((token) => {
                    const trimmed = token.trim();
                    if (!trimmed || ["+", "-", "*", "/", "(", ")", "^"].includes(trimmed)) {
                        return token;
                    }
                    return sanitizeNumberToken(token);
                })
                .join("")
        );
    }

    return sanitizeNumberToken(s);
}

function sanitizeNumberToken(token) {
    if (typeof token !== "string") {
        return token;
    }
    const t = token.trim();
    if (!t) {
        return token;
    }

    // Both comma and dot present
    if (t.includes(",") && t.includes(".")) {
        const lastDot = t.lastIndexOf(".");
        const lastComma = t.lastIndexOf(",");
        if (lastDot > lastComma) {
            // "25,000.50" -> dot is decimal point, commas are thousands separators
            return t.replace(/,/g, "");
        } else {
            // "25.000,50" -> dot is thousands separator, comma is decimal point
            return t.replace(/\./g, "").replace(/,/g, ".");
        }
    }

    // Only comma present
    if (t.includes(",")) {
        const parts = t.split(",");
        // Multiple commas: e.g. "1,00,000" or "10,00,000" or "1,000,000"
        if (parts.length > 2) {
            return t.replace(/,/g, "");
        }

        // Single comma: check digits immediately following the comma
        const digitsAfter = parts[1].replace(/\D/g, "");

        // If followed by exactly 3 digits (e.g. "25,000", "5,000", "30,000", "1,500"):
        // It is a thousands separator!
        if (digitsAfter.length === 3) {
            return t.replace(/,/g, "");
        }

        // If followed by 1 or 2 digits (e.g. "25,5", "25,50") with no dot:
        // Convert comma to dot for European decimal input compatibility
        if (digitsAfter.length === 1 || digitsAfter.length === 2) {
            return t.replace(/,/g, ".");
        }

        // Any other unusual count: strip comma
        return t.replace(/,/g, "");
    }

    return token;
}

// 1. Patch FloatField prototype
if (FloatField?.prototype) {
    patch(FloatField.prototype, {
        parse(value) {
            if (typeof value === "string") {
                value = sanitizeNumberComma(value);
            }
            return super.parse(value);
        },
    });
}

// 2. Patch MonetaryField prototype
if (MonetaryField?.prototype) {
    patch(MonetaryField.prototype, {
        parse(value) {
            if (typeof value === "string") {
                value = sanitizeNumberComma(value);
            }
            return parseFloat(value, { allowOperation: true });
        },
        get inputOptions() {
            const options = super.inputOptions;
            return {
                ...options,
                parse: (v) => this.parse(v),
            };
        },
    });
}

// 3. Patch ProgressBarField prototype
if (ProgressBarField?.prototype) {
    patch(ProgressBarField.prototype, {
        parseCurrentValue(value) {
            if (typeof value === "string") {
                value = sanitizeNumberComma(value);
            }
            return super.parseCurrentValue(value);
        },
    });
}

// 4. Wrap parsers in registry for any components accessing registry directly
const parsersRegistry = registry.category("parsers");
if (parsersRegistry) {
    if (parsersRegistry.contains("float")) {
        const origFloat = parsersRegistry.get("float");
        parsersRegistry.add(
            "float",
            (value, ...args) => {
                if (typeof value === "string") {
                    value = sanitizeNumberComma(value);
                }
                return origFloat(value, ...args);
            },
            { force: true }
        );
    }
    if (parsersRegistry.contains("monetary")) {
        const origMonetary = parsersRegistry.get("monetary");
        parsersRegistry.add(
            "monetary",
            (value, ...args) => {
                if (typeof value === "string") {
                    value = sanitizeNumberComma(value);
                }
                return origMonetary(value, ...args);
            },
            { force: true }
        );
    }
}
