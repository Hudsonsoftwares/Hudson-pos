import { ProductTemplate } from "@point_of_sale/app/models/product_template";
import { ComboConfiguratorPopup } from "@point_of_sale/app/components/popups/combo_configurator_popup/combo_configurator_popup";
import { ProductConfiguratorPopup } from "@point_of_sale/app/components/popups/product_configurator_popup/product_configurator_popup";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(ProductTemplate.prototype, {
    needToConfigure() {
        if (this.isCombo()) {
            return true;
        }
        if (this.isConfigurable()) {
            const activeLines = this.attribute_line_ids.filter((l) => l.active !== false);
            if (activeLines.length > 0) {
                // If there are multiple variants or attributes with multiple choices or no_variant attributes:
                if (
                    this.product_variant_ids.length > 1 ||
                    activeLines.some((l) => (l.product_template_value_ids?.length || 0) > 1) ||
                    activeLines.some((l) => l.attribute_id.create_variant === "no_variant")
                ) {
                    return true;
                }
            }
        }
        return super.needToConfigure();
    },
});

// ---------------------------------------------------------------------------
// Restrict the product configurator to the variants a combo actually offers.
// The combo popup sets this right before opening the configurator; the
// configurator captures it in setup(). Variants outside the set are flagged as
// "not available" (core warning) and the Add button is disabled.
// ---------------------------------------------------------------------------
let nextAllowedVariantIds = null;

async function withAllowedVariants(products, fn) {
    nextAllowedVariantIds = new Set(products.map((p) => p.id));
    try {
        return await fn();
    } finally {
        nextAllowedVariantIds = null;
    }
}

patch(ProductConfiguratorPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.allowedVariantIds = nextAllowedVariantIds;
        nextAllowedVariantIds = null;
    },
    isArchivedCombination() {
        if (super.isArchivedCombination()) {
            return true;
        }
        const hasVariants = this.attributes.some(
            (line) => line.attribute_id.create_variant !== "no_variant"
        );
        if (this.allowedVariantIds && hasVariants) {
            const product = this.product;
            return !product || !this.allowedVariantIds.has(product.id);
        }
        return false;
    },
});

patch(ComboConfiguratorPopup.prototype, {
    // One variant picker at a time: a double tap (or a second tap while the picker is still
    // opening) would otherwise stack two pickers, and pressing Add on the first one shows the
    // second one, as if the picker "reopened".
    async _withSinglePicker(fn) {
        if (this._pickerOpen) {
            return;
        }
        this._pickerOpen = true;
        try {
            return await fn();
        } finally {
            this._pickerOpen = false;
        }
    },

    // Same as core, except the picker is awaited (core fires it without awaiting) so the
    // single-picker guard holds until it is closed.
    async onClickProduct(product, combo_item) {
        return this._withSinglePicker(async () => {
            const productTmpl = product.product_tmpl_id;
            const combo = combo_item.combo_id;
            if (
                !this.state.qty[combo.id][combo_item.id] &&
                this.pos.isProductSnoozed(productTmpl) &&
                !(await this.pos.canAddProductToCurrentOrder(productTmpl))
            ) {
                return;
            }
            if (productTmpl.needToConfigure()) {
                await this.onClickConfigurableProduct(product, combo_item, combo);
            } else {
                this.onClickSimpleProduct(combo_item, combo);
            }
        });
    },

    // Same argument order and quantity rules as core (onClickProduct calls it with
    // (product, combo_item, combo)); changes: hideAlwaysVariants: false so every
    // variant attribute is shown, and only this combo item's variant is selectable.
    async onClickConfigurableProduct(product, combo_item, combo) {
        const isSingleQtyChoice = combo.qty_max === 1;
        if (this.totalQuantityForCombo(combo.id) >= combo.qty_max && !isSingleQtyChoice) {
            return;
        }
        if (this.state.qty[combo.id][combo_item.id] > 0 && !isSingleQtyChoice) {
            this.state.qty[combo.id][combo_item.id] += 1;
            return;
        }
        const allLines = this.props.line?.getAllLinesInCombo() || [];
        const line = allLines
            .filter((l) => l.combo_item_id)
            .find((l) => l.combo_item_id.id === combo_item.id);

        const payload = await withAllowedVariants([product], () =>
            this.pos.openConfigurator(product.product_tmpl_id, {
                hideAlwaysVariants: false,
                forceVariantValue: product.product_template_variant_value_ids,
                line,
                comboItem: combo_item,
            })
        );

        if (payload) {
            this.resetSingleQtyMaxCombo(combo);
            this.state.configuration[combo_item.id] = payload;
            this.state.qty[combo.id][combo_item.id] = 1;
        }
    },

    // -----------------------------------------------------------------------
    // Variant grouping: several combo items that are variants of the same
    // product template are shown as ONE card; clicking it opens the variant
    // picker and the chosen variant is mapped back to its combo item.
    // -----------------------------------------------------------------------
    getComboGroups(combo) {
        const groups = [];
        const byTmpl = new Map();
        for (const item of combo.combo_item_ids) {
            const product = item.product_id;
            if (!product) {
                continue;
            }
            const tmpl = product.product_tmpl_id;
            let group = tmpl && byTmpl.get(tmpl.id);
            if (!group) {
                group = { key: `t${tmpl?.id}_${item.id}`, tmpl, items: [] };
                groups.push(group);
                if (tmpl) {
                    byTmpl.set(tmpl.id, group);
                }
            }
            group.items.push(item);
        }
        // Only group when there really are several distinct variants.
        const result = [];
        for (const group of groups) {
            const distinct = new Set(group.items.map((i) => i.product_id.id));
            if (group.items.length > 1 && distinct.size > 1) {
                result.push(group);
            } else {
                for (const item of group.items) {
                    result.push({ key: `i${item.id}`, tmpl: group.tmpl, items: [item] });
                }
            }
        }
        return result;
    },

    groupQty(group) {
        const combo = group.items[0].combo_id;
        return group.items.reduce((acc, item) => acc + (this.state.qty[combo.id][item.id] || 0), 0);
    },

    getSelectedGroupItems(group) {
        const combo = group.items[0].combo_id;
        return group.items.filter((item) => this.state.qty[combo.id][item.id] > 0);
    },

    variantLabel(product) {
        const values = product.product_template_variant_value_ids || [];
        return values.map((v) => v.name).join(", ");
    },

    getGroupName(group) {
        const name = group.tmpl.name || group.tmpl.display_name;
        const selected = this.getSelectedGroupItems(group);
        if (selected.length === 1) {
            const label = this.variantLabel(selected[0].product_id);
            return label ? `${name} (${label})` : name;
        }
        if (selected.length > 1) {
            return `${name} (${selected.length} ${_t("options")})`;
        }
        return name;
    },

    formattedGroupPrice(group) {
        const selected = this.getSelectedGroupItems(group);
        if (selected.length === 1) {
            return this.formattedComboPrice(selected[0]);
        }
        const prices = group.items.map((i) => i.extra_price);
        const min = Math.min(...prices);
        const max = Math.max(...prices);
        if (this.pos.currency.isZero(max - min)) {
            return this.formattedComboPrice(group.items[0]);
        }
        const fmt = (v) =>
            this.pos.formatCurrency(v, this.pos.currency.id, { trailingZeros: false });
        if (this.pos.currency.isZero(min)) {
            return `+ ${_t("up to")} ${fmt(max)}`;
        }
        return `+ ${fmt(min)} - ${fmt(max)}`;
    },

    showGroupQuantityButtons(group) {
        return this.groupQty(group) > 0 && group.items[0].combo_id.qty_max > 1;
    },

    setGroupQuantity(group, quantity) {
        const current = this.groupQty(group);
        if (quantity > current) {
            this.onClickProductGroup(group);
        } else if (quantity < current) {
            const combo = group.items[0].combo_id;
            const selected = this.getSelectedGroupItems(group);
            let toRemove = current - quantity;
            for (const item of selected.reverse()) {
                if (toRemove <= 0) {
                    break;
                }
                const take = Math.min(toRemove, this.state.qty[combo.id][item.id]);
                this.state.qty[combo.id][item.id] -= take;
                toRemove -= take;
            }
        }
    },

    async onClickProductGroup(group) {
        return this._withSinglePicker(() => this._pickGroupVariant(group));
    },

    async _pickGroupVariant(group) {
        const combo = group.items[0].combo_id;
        const tmpl = group.tmpl;
        const isSingleQtyChoice = combo.qty_max === 1;
        if (!isSingleQtyChoice && this.totalQuantityForCombo(combo.id) >= combo.qty_max) {
            return;
        }
        if (
            !this.groupQty(group) &&
            this.pos.isProductSnoozed(tmpl) &&
            !(await this.pos.canAddProductToCurrentOrder(tmpl))
        ) {
            return;
        }
        const current = isSingleQtyChoice ? this.getSelectedGroupItems(group)[0] : undefined;
        const seed = current || group.items[0];
        const line = current
            ? (this.props.line?.getAllLinesInCombo() || []).find(
                  (l) => l.combo_item_id?.id === current.id
              )
            : undefined;

        const payload = await withAllowedVariants(
            group.items.map((i) => i.product_id),
            () =>
                this.pos.openConfigurator(tmpl, {
                    hideAlwaysVariants: false,
                    forceVariantValue: seed.product_id.product_template_variant_value_ids,
                    line,
                    comboItem: seed,
                })
        );
        if (!payload) {
            return;
        }
        const chosen = new Set(payload.attribute_value_ids || []);
        const item = group.items.find((i) =>
            (i.product_id.product_template_variant_value_ids || []).every((v) => chosen.has(v.id))
        );
        if (!item) {
            this.pos.notification.add(_t("This option is not available in this combo."), {
                type: "warning",
            });
            return;
        }
        if (isSingleQtyChoice) {
            this.resetSingleQtyMaxCombo(combo);
            this.state.qty[combo.id][item.id] = 1;
        } else {
            this.state.qty[combo.id][item.id] += 1;
        }
        this.state.configuration[item.id] = payload;
    },
});
