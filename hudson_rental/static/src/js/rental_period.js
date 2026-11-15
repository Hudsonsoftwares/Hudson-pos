import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { AddToCart } from "@website_sale/interactions/add_to_cart";

const PERIOD_SELECTOR = ".o_rental_period";

function toDateInput(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * Read the rental period chosen in the product page block, as UTC ISO strings.
 * Dates and times are entered in the visitor's (browser) timezone.
 */
export function getRentalPeriod(el) {
    const block = el.querySelector(PERIOD_SELECTOR);
    if (!block) {
        return {};
    }
    const read = (dateName, timeName) => {
        const date = block.querySelector(`input[name="${dateName}"]`).value;
        const hour = parseInt(block.querySelector(`select[name="${timeName}"]`).value) || 0;
        if (!date) {
            return undefined;
        }
        const [y, m, d] = date.split("-").map(Number);
        return new Date(y, m - 1, d, hour).toISOString();
    };
    return {
        rental_start_date: read("rental_start_date", "rental_pickup_hour"),
        rental_end_date: read("rental_end_date", "rental_return_hour"),
        rental_tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
}

/**
 * "Rental Period" block of a rental product page: shows the visitor's timezone and
 * proposes a first rental period (one period of the product's periodicity).
 */
export class RentalPeriod extends Interaction {
    static selector = PERIOD_SELECTOR;
    dynamicContent = {
        'input[name="rental_start_date"]': { "t-on-change": this.onStartChange },
    };

    setup() {
        this.startInput = this.el.querySelector('input[name="rental_start_date"]');
        this.endInput = this.el.querySelector('input[name="rental_end_date"]');
        this.pickupSelect = this.el.querySelector('select[name="rental_pickup_hour"]');
        this.returnSelect = this.el.querySelector('select[name="rental_return_hour"]');

        const offset = -new Date().getTimezoneOffset();
        const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, "0");
        this.el.querySelector(".o_rental_tz").textContent =
            `(UTC ${offset < 0 ? "-" : "+"} ${pad(offset / 60)}:${pad(offset % 60)})`;

        if (!this.startInput.value) {
            this.setDefaultPeriod();
        }
        this.startInput.min = toDateInput(new Date());
        this.endInput.min = this.startInput.value;
    }

    setDefaultPeriod() {
        const periodicity = this.el.dataset.periodicity;
        const now = new Date();
        const start = new Date(now);
        if (periodicity === "hour") {
            start.setHours(now.getHours() + 1, 0, 0, 0);
        } else {
            start.setHours(parseInt(this.el.dataset.pickupHour) || 0, 0, 0, 0);
            if (start <= now) {
                start.setDate(start.getDate() + 1);
            }
        }
        const end = new Date(start);
        if (periodicity === "hour") {
            end.setHours(end.getHours() + 1);
        } else {
            const days = { day: 1, week: 7, month: 0 }[periodicity] ?? 1;
            if (periodicity === "month") {
                end.setMonth(end.getMonth() + 1);
            } else {
                end.setDate(end.getDate() + days);
            }
            end.setHours(parseInt(this.el.dataset.returnHour) || 0);
        }
        this.startInput.value = toDateInput(start);
        this.endInput.value = toDateInput(end);
        this.pickupSelect.value = String(start.getHours());
        this.returnSelect.value = String(end.getHours());
    }

    onStartChange() {
        this.endInput.min = this.startInput.value;
        if (this.endInput.value < this.startInput.value) {
            this.endInput.value = this.startInput.value;
        }
    }
}

registry.category("public.interactions").add("hudson_rental.rental_period", RentalPeriod);

// The shop's "Add to cart" sends the chosen rental period along with the product
patch(AddToCart.prototype, {
    _getOptionalParams(el) {
        return { ...super._getOptionalParams(el), ...getRentalPeriod(el) };
    },
});
