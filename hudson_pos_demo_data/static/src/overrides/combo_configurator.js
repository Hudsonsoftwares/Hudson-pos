import { ProductTemplate } from "@point_of_sale/app/models/product_template";
import { ComboConfiguratorPopup } from "@point_of_sale/app/components/popups/combo_configurator_popup/combo_configurator_popup";
import { patch } from "@web/core/utils/patch";

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

patch(ComboConfiguratorPopup.prototype, {
    // Same argument order and quantity rules as core (onClickProduct calls it with
    // (product, combo_item, combo)); the only change is hideAlwaysVariants: false so
    // every variant attribute is shown in the configurator.
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

        const payload = await this.pos.openConfigurator(product.product_tmpl_id, {
            hideAlwaysVariants: false,
            forceVariantValue: product.product_template_variant_value_ids,
            line,
            comboItem: combo_item,
        });

        if (payload) {
            this.resetSingleQtyMaxCombo(combo);
            this.state.configuration[combo_item.id] = payload;
            this.state.qty[combo.id][combo_item.id] = 1;
        }
    },
});
