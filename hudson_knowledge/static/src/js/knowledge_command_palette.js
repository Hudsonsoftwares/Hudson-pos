/** @odoo-module **/

/**
 * Knowledge in every app (like Odoo Online):
 *  - "?" namespace of the command palette searches the articles
 *    (shows up as "?articles" in the palette's TIP footer);
 *  - a Knowledge (bookmark) button in the control panel of every form view
 *    with a chatter opens the palette on that namespace.
 * The article opens in the Knowledge client action pushed on top of the
 * current breadcrumbs, so the user can go back to the record (bill, sale
 * order, ...) and stays in the current app.
 */

import { Component, onWillStart, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useSubEnv } from "@web/owl2/utils";
import { patch } from "@web/core/utils/patch";
import { defaultCommandItemProps } from "@web/core/commands/command_palette";
import { HotkeyCommandItem } from "@web/core/commands/default_providers";
import { FormController } from "@web/views/form/form_controller";

export const KNOWLEDGE_NAMESPACE = "?";
const KNOWLEDGE_ACTION_TAG = "hudson_knowledge.action_knowledge";

export class KnowledgeArticleCommand extends Component {
    static template = "hudson_knowledge.KnowledgeArticleCommand";
    props = useProps({
        icon: t.string().optional(),
        isFavorite: t.boolean().optional(),
        parentPath: t.string().optional(),
        ...defaultCommandItemProps,
    });
}

registry.category("command_setup").add(KNOWLEDGE_NAMESPACE, {
    debounceDelay: 200,
    emptyMessage: _t("No article found"),
    name: _t("articles"),
    placeholder: _t("Search for an article or a keyword..."),
});

const commandCategoryRegistry = registry.category("command_categories");
commandCategoryRegistry.add(
    "knowledge_articles",
    { namespace: KNOWLEDGE_NAMESPACE },
    { sequence: 10 }
);
commandCategoryRegistry.add(
    "knowledge_advanced_search",
    { namespace: KNOWLEDGE_NAMESPACE },
    { sequence: 20 }
);

/** Opens an article in the Knowledge app, on top of the current breadcrumbs. */
export function openKnowledgeArticle(actionService, articleId) {
    return actionService.doAction({
        type: "ir.actions.client",
        tag: KNOWLEDGE_ACTION_TAG,
        name: _t("Knowledge"),
        params: { article_id: articleId },
    });
}

registry.category("command_provider").add("knowledge_articles", {
    namespace: KNOWLEDGE_NAMESPACE,
    provide(options) {
        // Services must be fetched synchronously (inside the palette's scope).
        const orm = useService("orm");
        const actionService = useService("action");
        const searchValue = (options.searchValue || "").trim();
        const advancedSearch = {
            Component: HotkeyCommandItem,
            action() {
                actionService.doAction({
                    type: "ir.actions.act_window",
                    name: _t("Search Articles"),
                    res_model: "knowledge.management.article",
                    views: [
                        [false, "list"],
                        [false, "form"],
                    ],
                    domain: [
                        ["active", "=", true],
                        ["is_article_item", "=", false],
                        ...(searchValue ? [["name", "ilike", searchValue]] : []),
                    ],
                    target: "current",
                });
            },
            category: "knowledge_advanced_search",
            name: _t("Advanced Search"),
            props: { hotkey: "alt+b" },
        };
        return orm
            .call("knowledge.management.article", "get_command_palette_articles", [], {
                search_term: searchValue,
                limit: 10,
            })
            .then((articles) => [
                ...articles.map((article) => ({
                    Component: KnowledgeArticleCommand,
                    action() {
                        openKnowledgeArticle(actionService, article.id);
                    },
                    category: "knowledge_articles",
                    name: article.name,
                    href: `/odoo/action-hudson_knowledge.action_knowledge_home?article_id=${article.id}`,
                    props: {
                        icon: article.icon || "",
                        isFavorite: article.is_user_favorite,
                        parentPath: article.parent_path || "",
                    },
                })),
                advancedSearch,
            ]);
    },
});

// ── Knowledge button in the control panel of form views ──────────────
// The button lives in the ControlPanel template (next to the pager); the
// form controller enables it through a sub-env when its arch has a chatter.
patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        const hasChatter =
            this.props.resModel !== "knowledge.management.article" &&
            Boolean(this.archInfo?.xmlDoc?.querySelector("chatter, div.oe_chatter"));
        if (hasChatter && !this.env.inDialog) {
            const commandService = useService("command");
            const button = {
                visible: false,
                open: () => commandService.openMainPalette({ searchValue: KNOWLEDGE_NAMESPACE }),
            };
            // Only Knowledge users can read articles (hasGroup is cached).
            onWillStart(async () => {
                button.visible = await user.hasGroup("hudson_knowledge.group_knowledge_user");
            });
            useSubEnv({ knowledgeFormButton: button });
        } else if (this.env.knowledgeFormButton) {
            // Don't leak the parent's button into nested forms.
            useSubEnv({ knowledgeFormButton: null });
        }
    },
});
