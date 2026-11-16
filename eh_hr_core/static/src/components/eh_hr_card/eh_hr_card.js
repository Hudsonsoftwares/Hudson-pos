/** @odoo-module **/
/**
 * <HrCard> - the platform's base card primitive.
 *
 * Every dashboard tile, drawer, list-detail panel and form section in the
 * EH HR Platform composes <HrCard> rather than re-implementing markup.
 */
import { Component } from "@odoo/owl";

export class HrCard extends Component {
    static template = "eh_hr_core.HrCard";
    static props = {
        tone:    { type: String, optional: true },
        compact: { type: Boolean, optional: true },
        loading: { type: Boolean, optional: true },
        slots:   { type: Object, optional: true },
    };
    static defaultProps = { tone: "default", compact: false, loading: false };

    get toneClass() {
        return `o_hrp_card o_hrp_card--${this.props.tone}` +
               (this.props.compact ? " o_hrp_card--compact" : "");
    }
}
