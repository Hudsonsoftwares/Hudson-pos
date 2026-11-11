/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PivotModel } from "@web/views/pivot/pivot_model";

patch(PivotModel.prototype, {
    _getMeasurements(group, config) {
        const measurements = super._getMeasurements(group, config);
        const { metaData } = config;
        for (const measureName of this._getMeasureSpecs(config)) {
            const [fieldName, aggregator] = measureName.split(":");
            if (
                aggregator === "sum_currency" &&
                measurements[fieldName] === undefined &&
                group[measureName] !== undefined
            ) {
                let measurement = group[measureName];
                if (
                    metaData.measures[fieldName]?.type === "boolean" &&
                    typeof measurement === "boolean"
                ) {
                    measurement = measurement ? 1 : 0;
                }
                measurements[fieldName] = measurement;
            }
        }
        return measurements;
    },
});
