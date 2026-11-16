/** @odoo-module **/
import { Component } from "@odoo/owl";

export class HrStat extends Component {
    static template = "eh_hr_core.HrStat";
    static props = {
        label: String,
        value: { type: [String, Number] },
        unit:  { type: String, optional: true },
        delta: { type: Number, optional: true },
        tone:  { type: String, optional: true },
    };
    static defaultProps = { tone: "neutral" };

    get deltaSign() {
        if (this.props.delta === undefined || this.props.delta === 0) return "";
        return this.props.delta > 0 ? "▲" : "▼";
    }
    get deltaClass() {
        if (this.props.delta === undefined) return "";
        if (this.props.delta > 0) return "o_hrp_stat__delta--up";
        if (this.props.delta < 0) return "o_hrp_stat__delta--down";
        return "";
    }
}
