/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, proxy, useProps, xml } from "@odoo/owl";
import { SpreadsheetComponent } from "@spreadsheet/actions/spreadsheet_component";
import { Model } from "@odoo/o-spreadsheet";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { _t } from "@web/core/l10n/translation";

class QualitySpreadsheetAction extends Component {
    static template = xml`
        <div class="o_spreadsheet_action h-100 d-flex flex-column">
            <ControlPanel display="this.controlPanelDisplay" />
            <div class="flex-grow-1 position-relative">
                <t t-if="this.state.model">
                    <SpreadsheetComponent model="this.state.model" />
                </t>
            </div>
        </div>
    `;
    static components = { SpreadsheetComponent, ControlPanel };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ model: null });
        
        this.controlPanelDisplay = {};

        onWillStart(async () => {
            const resModel = this.props.action.params.res_model || "quality.spreadsheet.template";
            this.resModel = resModel;
            const spreadsheetId = this.props.action.params.spreadsheet_id || this.props.action.context.active_id;
            this.spreadsheetId = spreadsheetId;
            const dataField = resModel === "quality.spreadsheet.template" ? "spreadsheet_binary_data" : "spreadsheet_content";
            const data = await this.orm.read(resModel, [spreadsheetId], [dataField, "name"]);
            
            this.env.config.setDisplayName(data[0].name || _t("Spreadsheet"));

            let spreadsheetData = {};
            if (data[0][dataField]) {
                try {
                    let rawData = data[0][dataField];
                    // Odoo 20 reads Binary fields as { content: <base64>, size, filename? }
                    if (rawData && typeof rawData === "object" && "content" in rawData) {
                        rawData = rawData.content;
                    }
                    // If it's base64 encoded (which doesn't start with { or [), we decode it
                    if (typeof rawData === 'string' && !rawData.trim().startsWith('{') && !rawData.trim().startsWith('[')) {
                        const binaryStr = atob(rawData);
                        const bytes = Uint8Array.from(binaryStr, (c) => c.charCodeAt(0));
                        rawData = new TextDecoder().decode(bytes);
                    }
                    spreadsheetData = JSON.parse(rawData);
                } catch (e) {
                    console.error("Invalid spreadsheet data", e);
                }
            }
            
            this.state.model = new Model(spreadsheetData, {
                evalContext: { env: this.env },
            });
            
            this.state.model.on("update", this, this._onModelUpdate.bind(this));
        });

        onWillUnmount(() => {
            if (this.saveTimeout) {
                clearTimeout(this.saveTimeout);
                // Save immediately using the raw service to avoid 'Component is destroyed' error
                this._saveRaw();
            }
        });
    }

    async _saveRaw() {
        if (!this.state.model) return;
        const data = this.state.model.exportData();
        const jsonStr = JSON.stringify(data);
        
        if (this.resModel === "quality.spreadsheet.template") {
            const bytes = new TextEncoder().encode(jsonStr);
            const binaryStr = Array.from(bytes).map(b => String.fromCharCode(b)).join('');
            const base64Data = btoa(binaryStr);
            this.env.services.orm.write(this.resModel, [this.spreadsheetId], {
                spreadsheet_binary_data: base64Data
            });
        } else {
            this.env.services.orm.write(this.resModel, [this.spreadsheetId], {
                spreadsheet_content: jsonStr
            });
        }
    }

    _onModelUpdate() {
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
        this.saveTimeout = setTimeout(() => {
            this.saveTimeout = null;
            this.save();
        }, 2000); // 2 second debounce for auto-save
    }

    async save() {
        if (!this.state.model) return;
        const data = this.state.model.exportData();
        const jsonStr = JSON.stringify(data);
        
        if (this.resModel === "quality.spreadsheet.template") {
            const bytes = new TextEncoder().encode(jsonStr);
            const binaryStr = Array.from(bytes).map(b => String.fromCharCode(b)).join('');
            const base64Data = btoa(binaryStr);
            await this.orm.write(this.resModel, [this.spreadsheetId], {
                spreadsheet_binary_data: base64Data
            });
        } else {
            await this.orm.write(this.resModel, [this.spreadsheetId], {
                spreadsheet_content: jsonStr
            });
        }
    }
}

registry.category("actions").add("action_quality_spreadsheet", QualitySpreadsheetAction, { force: true });
