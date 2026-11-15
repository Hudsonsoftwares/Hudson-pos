import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";

// Filters always kept with a card's own filter (see the search view)
const DEFAULT_FILTERS = ["rentals"];

/**
 * Counters above the rental orders list, like Odoo's Rental app.
 * Clicking a card shows the matching orders; clicking it again goes back to all rentals.
 */
export class RentalDashboard extends Component {
    static template = "hudson_rental.RentalDashboard";
    props = useProps(); // list: the rental orders list shown below

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ data: {}, selectedCard: "" });
        const reload = useDebounced(() => this.loadData(), 200);

        useBus(this.env.searchModel, "update", () => {
            this.state.selectedCard =
                this.cards.find((card) => this.isActiveFilter([card.key, ...DEFAULT_FILTERS]))?.key || "";
            reload();
        });
        // The list view is kept alive (e.g. coming back from an order through the
        // breadcrumbs): refresh the counters whenever its records are (re)loaded.
        useBus(this.props.list.model.bus, "update", reload);
        onWillStart(() => this.loadData());
    }

    get leftCards() {
        return [
            { key: "today", label: _t("Today"), color: "gray" },
            { key: "pickups", label: _t("Pickups"), color: "purple" },
            { key: "returns", label: _t("Returns"), color: "pink" },
            { key: "late", label: _t("Late"), color: "red" },
        ];
    }

    get rightCards() {
        return [
            { key: "to_confirm", label: _t("To Confirm"), color: "orange" },
            { key: "to_invoice", label: _t("To Invoice"), color: "cyan" },
        ];
    }

    get cards() {
        return [...this.leftCards, ...this.rightCards];
    }

    async loadData() {
        this.state.data = await this.orm.call("sale.order", "retrieve_rental_dashboard", []);
    }

    onCardClick(card) {
        const filters =
            this.state.selectedCard === card.key ? DEFAULT_FILTERS : [card.key, ...DEFAULT_FILTERS];
        const searchItems = this.env.searchModel.getSearchItems((item) => filters.includes(item.name));
        this.env.searchModel.query.length = 0;
        for (const item of searchItems) {
            this.env.searchModel.toggleSearchItem(item.id);
        }
    }

    isActiveFilter(filters) {
        const active = this.env.searchModel
            .getSearchItems((item) => item.isActive && item.type === "filter")
            .map((item) => item.name);
        return active.length === filters.length && filters.every((name) => active.includes(name));
    }

    cardClass(card) {
        return `o_rental_card_${card.color}` + (this.state.selectedCard === card.key ? " active" : "");
    }
}

export class RentalDashboardListRenderer extends ListRenderer {
    static template = "hudson_rental.RentalDashboardListRenderer";
    static components = { ...ListRenderer.components, RentalDashboard };
}

export const rentalDashboardListView = {
    ...listView,
    Renderer: RentalDashboardListRenderer,
};

registry.category("views").add("rental_dashboard_list", rentalDashboardListView);
