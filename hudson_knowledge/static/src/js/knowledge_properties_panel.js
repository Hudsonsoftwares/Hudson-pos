/** @odoo-module **/

/**
 * Knowledge article properties panel (Odoo Online "Add Properties").
 *
 * The parent article holds the properties definition, shared by all its
 * sub-articles; each article stores its own values. The panel embeds Odoo's
 * standard Properties field on a standalone record of the open article, so
 * the "Add Property Field" editor, the property types, tags, etc. are the
 * standard ones. Changes are saved right away (once the property editor is
 * closed).
 */

import { Component, EventBus, onMounted, onWillUnmount, onWillUpdateProps, t, useProps } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { Record } from "@web/model/record";
import { useSubEnv } from "@web/owl2/utils";
import { PropertiesField } from "@web/views/fields/properties/properties_field";

const CREATE_EVENT = "KNOWLEDGE_PROPERTIES:CREATE";

/**
 * Standard Properties field that can be asked to create a new property
 * ("Add Properties" in the article menu).
 */
export class KnowledgePropertiesField extends PropertiesField {
    setup() {
        super.setup();
        const shared = this.env.knowledgeProperties;
        if (!shared) {
            return;
        }
        shared.field = this;
        useBus(shared.bus, CREATE_EVENT, () => this._knowledgeMaybeCreate());
        onMounted(() => this._knowledgeMaybeCreate());
        onWillUnmount(() => {
            if (shared.field === this) {
                shared.field = null;
            }
        });
    }

    async _knowledgeMaybeCreate() {
        const shared = this.env.knowledgeProperties;
        if (!shared?.consumeCreateRequest() || this.props.readonly) {
            return;
        }
        let canChangeDefinition = this.state.canChangeDefinition;
        if (!canChangeDefinition) {
            canChangeDefinition = await this.checkDefinitionWriteAccess();
        }
        if (!canChangeDefinition) {
            this.notification.add(this._getPropertyEditWarningText(), { type: "warning" });
            return;
        }
        this.state.canChangeDefinition = true;
        this.setEditMode(true);
        await this.onPropertyCreate();
    }
}

export class KnowledgePropertiesPanel extends Component {
    static template = "hudson_knowledge.KnowledgePropertiesPanel";
    static components = { Record, KnowledgePropertiesField };
    props = useProps({
        articleId: t.number(),
        readonly: t.boolean().optional(false),
        createRequest: t.number().optional(0),
        consumeCreateRequest: t.any().optional(),
        registerPanel: t.any().optional(),
        onSaved: t.any().optional(),
        onClose: t.any().optional(),
    });

    setup() {
        this.fieldNames = ["article_properties", "parent_id"];
        this.record = null;
        this._saveTimer = null;
        this._savePromise = null;
        this.recordHooks = {
            onRootLoaded: (root) => {
                this.record = root;
            },
            onRecordChanged: () => this._scheduleSave(),
        };
        this.shared = {
            bus: new EventBus(),
            field: null,
            consumeCreateRequest: () => !!this.props.consumeCreateRequest?.(),
        };
        useSubEnv({ knowledgeProperties: this.shared });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.articleId !== this.props.articleId) {
                // Save the previous article's properties before switching.
                await this.flush();
            }
            if (nextProps.createRequest !== this.props.createRequest) {
                setTimeout(() => this.shared.bus.trigger(CREATE_EVENT));
            }
        });
        this.props.registerPanel?.(this);
        onWillUnmount(() => {
            clearTimeout(this._saveTimer);
            this.props.registerPanel?.(null, this);
        });
    }

    get recordMode() {
        return this.props.readonly ? "readonly" : "edit";
    }

    /** The property editor popover is open: the definition is being edited. */
    get isEditingDefinition() {
        return !!(
            this.shared.field?.state?.isPopoverOpen ||
            document.querySelector(".o_property_field_popover")
        );
    }

    _scheduleSave() {
        clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(() => {
            if (this.isEditingDefinition) {
                // Wait for "Add" / "Discard" before saving the definition.
                this._scheduleSave();
                return;
            }
            this.flush();
        }, 250);
    }

    /** Save pending changes (skipped while a property is being edited). */
    async flush() {
        if (this._savePromise) {
            await this._savePromise.catch(() => {});
        }
        const record = this.record;
        if (!record || this.props.readonly) {
            return;
        }
        if (this.isEditingDefinition) {
            // Keep waiting: saved once the property editor is closed.
            this._scheduleSave();
            return;
        }
        clearTimeout(this._saveTimer);
        this._savePromise = (async () => {
            try {
                if (await record.isDirty()) {
                    await record.save();
                }
                const values = record.data.article_properties || [];
                this.props.onSaved?.(this.props.articleId, values.length > 0);
            } finally {
                this._savePromise = null;
            }
        })();
        return this._savePromise;
    }

    async onClickClose() {
        await this.flush();
        this.props.onClose?.();
    }
}
