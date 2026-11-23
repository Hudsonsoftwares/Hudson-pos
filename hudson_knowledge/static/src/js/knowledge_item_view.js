/** @odoo-module **/
/**
 * Article Items embedded views (Odoo Online style).
 *
 * "Build an Item Kanban / List / Calendar" inserts a host element in the
 * article body:
 *
 *   <div data-embedded="knowledgeItemView" data-oe-protected="true"
 *        contenteditable="false"
 *        data-embedded-props='{"viewType": "kanban", "name": "Tasks"}'/>
 *
 * The html_editor EmbeddedComponentPlugin (or the HtmlViewer when the article
 * is locked) mounts KnowledgeItemView on it, which renders the real Odoo
 * kanban / list / calendar view of the child "item" articles of the current
 * article: stages, drag & drop, quick create, column creation, folding,
 * optional columns, search, filters, group by... exactly like in Odoo.
 */

import { Component, onWillStart, proxy, useProps, markup } from "@odoo/owl";
import { useSubEnv } from "@web/owl2/utils";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { View, getDefaultConfig } from "@web/views/view";
import { calendarView } from "@web/views/calendar/calendar_view";
import { CalendarController } from "@web/views/calendar/calendar_controller";
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { serializeDateTime } from "@web/core/l10n/dates";

export const ITEM_VIEW_EMBEDDING_NAME = "knowledgeItemView";
const ARTICLE_MODEL = "knowledge.management.article";

// ─────────────────────────────────────────────────────────────────
// Calendar: open / create items as articles inside Knowledge
// ─────────────────────────────────────────────────────────────────
export class KnowledgeItemCalendarController extends CalendarController {
    /**
     * Clicking / selecting a slot creates an item article (dated on that
     * slot so it shows in the calendar) and opens it, like the kanban and
     * list "New" — no event quick-create dialog.
     */
    async createRecord(record) {
        if (!this.model.canCreate || !this.env.createKnowledgeItem) {
            return super.createRecord(record);
        }
        const rawRecord = this.model.buildRawRecord(record);
        const context = this.model.makeContextDefaults(rawRecord);
        delete context.default_name;
        return this.env.createKnowledgeItem(context);
    }

    async editRecord(record, context = {}) {
        if (record.id && this.env.openKnowledgeItem) {
            return this.env.openKnowledgeItem(record.id);
        }
        if (!record.id && this.env.createKnowledgeItem) {
            return this.env.createKnowledgeItem(context);
        }
        return super.editRecord(record, context);
    }

    /** "New" button: create an item starting at the next hour and open it. */
    async onKnowledgeNewItem() {
        const start = luxon.DateTime.local().plus({ hours: 1 }).startOf("hour");
        await this.env.createKnowledgeItem?.({
            default_item_date_start: serializeDateTime(start),
            default_item_date_end: serializeDateTime(start.plus({ hours: 1 })),
        });
    }
}

registry.category("views").add("knowledge_item_calendar", {
    ...calendarView,
    Controller: KnowledgeItemCalendarController,
    buttonTemplate: "hudson_knowledge.KnowledgeItemCalendar.controlButtons",
});

// ─────────────────────────────────────────────────────────────────
// Embedded view component
// ─────────────────────────────────────────────────────────────────
let itemViewIdsPromise = null;

function loadItemViewIds(orm) {
    if (!itemViewIdsPromise) {
        itemViewIdsPromise = orm.call(ARTICLE_MODEL, "get_item_view_ids", []).catch((e) => {
            itemViewIdsPromise = null;
            throw e;
        });
    }
    return itemViewIdsPromise;
}

const VIEW_LABELS = {
    kanban: _t("Item Kanban"),
    list: _t("Item List"),
    calendar: _t("Item Calendar"),
};

export class KnowledgeItemView extends Component {
    static template = "hudson_knowledge.KnowledgeItemView";
    static components = { View };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ viewIds: null, error: false });

        const config = getDefaultConfig();
        // Never steal the caret from the article editor.
        config.disableSearchBarAutofocus = true;
        config.setDisplayName(this.displayName);
        useSubEnv({
            config,
            openKnowledgeItem: (resId) => this.openItem(resId),
            createKnowledgeItem: (context) => this.createItem(context),
        });

        onWillStart(async () => {
            if (!this.parentId) {
                this.state.error = true;
                return;
            }
            try {
                this.state.viewIds = await loadItemViewIds(this.orm);
            } catch (e) {
                console.error("Knowledge: could not load the item views", e);
                this.state.error = true;
            }
        });
    }

    get viewType() {
        return ["kanban", "list", "calendar"].includes(this.props.viewType)
            ? this.props.viewType
            : "kanban";
    }

    get displayName() {
        return this.props.name || VIEW_LABELS[this.viewType];
    }

    get parentId() {
        return this.props.parentId;
    }

    get readonly() {
        return Boolean(this.props.readonly);
    }

    get itemContext() {
        const context = {
            default_parent_id: this.parentId,
            default_is_article_item: true,
            // Empty title in the quick create (instead of the "Untitled" default)
            default_name: "",
            active_id: this.parentId,
            active_model: ARTICLE_MODEL,
        };
        if (this.readonly) {
            Object.assign(context, {
                create: false,
                edit: false,
                delete: false,
                group_create: false,
                group_edit: false,
                group_delete: false,
            });
        }
        return context;
    }

    get viewProps() {
        const ids = this.state.viewIds || {};
        const type = this.viewType;
        return {
            resModel: ARTICLE_MODEL,
            type,
            viewId: ids[type] || false,
            views: [
                [ids[type] || false, type],
                [ids.search || false, "search"],
            ],
            searchViewId: ids.search || false,
            context: this.itemContext,
            domain: [
                ["parent_id", "=", this.parentId],
                ["is_article_item", "=", true],
            ],
            display: { controlPanel: {} },
            loadIrFilters: false,
            loadActionMenus: false,
            useSampleModel: false,
            noContentHelp: type !== "list" ? undefined : markup(
                `<p class="o_view_nocontent_smiling_face">${_t("No items yet")}</p>` +
                    `<p>${_t("Create an item to start organizing the content of this article.")}</p>`
            ),
            selectRecord: (resId) => this.openItem(resId),
            createRecord: () => this.createItem(),
        };
    }

    async openItem(resId) {
        await this.props.knowledgeAction?.openItemArticle(resId);
    }

    async createItem(extraContext = {}) {
        if (this.readonly) {
            return;
        }
        const context = { ...this.itemContext, ...extraContext };
        const vals = {
            parent_id: this.parentId,
            is_article_item: true,
            name: context.default_name || _t("Untitled"),
        };
        for (const [key, value] of Object.entries(context)) {
            if (key.startsWith("default_item_date_") || key === "default_stage_id") {
                vals[key.slice("default_".length)] = value;
            }
        }
        const [resId] = await this.orm.create(ARTICLE_MODEL, [vals], {
            context: { default_parent_id: this.parentId, default_is_article_item: true },
        });
        await this.openItem(resId);
    }
}

/**
 * @param {Object} knowledgeAction the Knowledge client action
 * @param {boolean} readonly
 */
export function getItemViewEmbedding(knowledgeAction, readonly = false) {
    return {
        name: ITEM_VIEW_EMBEDDING_NAME,
        Component: KnowledgeItemView,
        getProps: (host) => ({
            ...getEmbeddedProps(host),
            parentId: knowledgeAction.state.currentArticle?.id,
            knowledgeAction,
            readonly,
        }),
    };
}

/**
 * @param {Document} doc
 * @param {"kanban"|"list"|"calendar"} viewType
 * @param {string} name
 * @returns {HTMLElement} the embedded view host
 */
export function createItemViewHost(doc, viewType, name) {
    const host = doc.createElement("div");
    host.className = "o_knowledge_item_view_host";
    host.dataset.embedded = ITEM_VIEW_EMBEDDING_NAME;
    host.dataset.oeProtected = "true";
    host.setAttribute("contenteditable", "false");
    host.dataset.embeddedProps = JSON.stringify({ viewType, name });
    return host;
}

/**
 * Converts the old hand-made embedded blocks (pre 20.0.1.0.15) into
 * embedded Odoo view hosts.
 * @param {string} html
 * @returns {string}
 */
export function upgradeLegacyItemViews(html) {
    if (!html || !/o_knowledge_embedded_view_(container|block)/.test(html)) {
        return html;
    }
    const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
    const legacyBlocks = doc.body.querySelectorAll(
        ".o_knowledge_embedded_view_container, .o_knowledge_embedded_view_block"
    );
    for (const block of legacyBlocks) {
        if (!block.isConnected) {
            continue;
        }
        const viewType = block.dataset.viewType || "kanban";
        const name = block.dataset.viewName || "";
        block.replaceWith(createItemViewHost(doc, viewType, name));
    }
    return doc.body.innerHTML;
}
