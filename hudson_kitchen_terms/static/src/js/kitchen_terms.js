/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { LazyTranslatedString } from "@web/core/l10n/translation";
import { session } from "@web/env";

if (session && session.kitchen_mode && session.kitchen_terms) {
    const terms = session.kitchen_terms;
    const sortedKeys = Object.keys(terms).sort((a, b) => b.length - a.length);
    const regexList = sortedKeys.map((key) => {
        const left = /^[a-zA-Z0-9]/.test(key) ? '\\b' : '(?:^|\\s)';
        const right = /[a-zA-Z0-9]$/.test(key) ? '\\b' : '(?:$|\\s)';
        const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return {
            regex: new RegExp(`${left}${escaped}${right}`, 'gi'),
            replacement: terms[key],
        };
    });

    function applyKitchenTerms(str) {
        if (!str || typeof str !== 'string') {
            return str;
        }
        let result = str;
        for (const { regex, replacement } of regexList) {
            result = result.replace(regex, (match) => {
                if (match === match.toUpperCase()) {
                    return replacement.toUpperCase();
                } else if (match === match.toLowerCase()) {
                    return replacement.toLowerCase();
                } else if (match[0] === match[0].toUpperCase() && match.slice(1) === match.slice(1).toLowerCase()) {
                    return replacement.charAt(0).toUpperCase() + replacement.slice(1);
                }
                return replacement;
            });
        }
        return result;
    }

    try {
        patch(LazyTranslatedString.prototype, {
            translate() {
                const res = super.translate(...arguments);
                if (typeof res === 'string') {
                    return applyKitchenTerms(res);
                }
                return res;
            },
        });
    } catch (e) {
        console.warn("[KitchenTerms] Could not patch LazyTranslatedString:", e);
    }
}
