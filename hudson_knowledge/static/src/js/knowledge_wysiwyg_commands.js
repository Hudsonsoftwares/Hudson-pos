/** @odoo-module **/

import { Plugin } from "@html_editor/plugin";
import { _t } from "@web/core/l10n/translation";
import { withSequence } from "@html_editor/utils/resource";
import { registry } from "@web/core/registry";

/**
 * The AI article generator is provided by the Hudson AI module. Its assets are
 * only in the bundle when it is installed in this database, so the presence of
 * its "Ask AI" systray item tells us whether the feature can be offered.
 */
export function isHudsonAIAvailable() {
    return registry.category("systray").contains("hudson_ai.systray");
}

/**
 * KnowledgeEditorPlugin
 *
 * Extends the Odoo html_editor with custom Knowledge commands:
 *  - Load a Template
 *  - Build an Item Kanban
 *  - Build an Item List
 *  - Build an Item Calendar
 *  - Generate an Article with AI
 *
 * These commands appear in the Powerbox when typing "/" anywhere in the article,
 * and the AI command also appears in the empty-line power buttons row.
 * The AI command is only offered when the Hudson AI module is installed.
 */
export class KnowledgeEditorPlugin extends Plugin {
    static id = "knowledgeEditor";
    static dependencies = ["selection", "history", "userCommand", "powerbox"];

    resources = {
        on_content_updated_handlers: () => this._ensureLineAfterImages(),
        powerbox_categories: [
            withSequence(45, { id: "knowledge", name: _t("Knowledge") }),
        ],
        user_commands: [
            {
                id: "knowledgeLoadTemplate",
                title: _t("Load a Template"),
                description: _t("Insert content from a saved template"),
                icon: "brush",
                run: () => {
                    if (this.config.knowledgeAction) {
                        this.config.knowledgeAction.onBrowseTemplates();
                    }
                },
            },
            {
                id: "knowledgeBuildItemKanban",
                title: _t("Build an Item Kanban"),
                description: _t("Create an interactive Kanban board inside this article"),
                icon: "view_kanban",
                run: () => {
                    if (this.config.knowledgeAction) {
                        this.config.knowledgeAction.openInsertViewModal("kanban", this._getTargetBlock());
                    }
                },
            },
            {
                id: "knowledgeBuildItemList",
                title: _t("Build an Item List"),
                description: _t("Create an interactive list inside this article"),
                icon: "format_list_bulleted",
                run: () => {
                    if (this.config.knowledgeAction) {
                        this.config.knowledgeAction.openInsertViewModal("list", this._getTargetBlock());
                    }
                },
            },
            {
                id: "knowledgeBuildItemCalendar",
                title: _t("Build an Item Calendar"),
                description: _t("Create an interactive calendar inside this article"),
                icon: "calendar_today",
                run: () => {
                    if (this.config.knowledgeAction) {
                        this.config.knowledgeAction.openInsertViewModal("calendar", this._getTargetBlock());
                    }
                },
            },
            ...(isHudsonAIAvailable()
                ? [
                      {
                          id: "knowledgeGenerateArticleAI",
                          title: _t("Generate an Article with AI"),
                          description: _t("Generate structured article content using AI"),
                          icon: "wand_stars",
                          run: () => {
                              if (this.config.knowledgeAction) {
                                  this.config.knowledgeAction.onOpenAIGenerator();
                              }
                          },
                      },
                  ]
                : []),
        ],
        powerbox_items: [
            withSequence(10, {
                categoryId: "knowledge",
                commandId: "knowledgeLoadTemplate",
                keywords: [_t("template"), _t("load"), _t("preset")],
            }),
            withSequence(20, {
                categoryId: "knowledge",
                commandId: "knowledgeBuildItemKanban",
                keywords: [_t("kanban"), _t("board"), _t("item"), _t("columns")],
            }),
            withSequence(30, {
                categoryId: "knowledge",
                commandId: "knowledgeBuildItemList",
                keywords: [_t("list"), _t("item"), _t("table"), _t("grid")],
            }),
            withSequence(40, {
                categoryId: "knowledge",
                commandId: "knowledgeBuildItemCalendar",
                keywords: [_t("calendar"), _t("date"), _t("schedule"), _t("item")],
            }),
            ...(isHudsonAIAvailable()
                ? [
                      withSequence(50, {
                          categoryId: "knowledge",
                          commandId: "knowledgeGenerateArticleAI",
                          keywords: [_t("ai"), _t("generate"), _t("magic"), _t("write")],
                      }),
                  ]
                : []),
        ],
        power_buttons: isHudsonAIAvailable()
            ? [
                  withSequence(85, {
                      commandId: "knowledgeGenerateArticleAI",
                      description: _t("Generate an Article with AI"),
                      icon: "wand_stars",
                  }),
              ]
            : [],
    };

    /**
     * An image alone in its block leaves nowhere to put the cursor after it.
     * When such a block is the last one of the article, add an empty paragraph
     * below so a description / further text can be typed under the image.
     */
    _ensureLineAfterImages() {
        try {
            const editable = this.editable;
            if (!editable || !editable.isContentEditable) {
                return;
            }
            const last = editable.lastElementChild;
            if (!last || !last.querySelector || !last.querySelector("img")) {
                return;
            }
            if (!["P", "DIV", "IMG"].includes(last.tagName)) {
                return;
            }
            if (last.textContent.replace(/[​﻿\s]/g, "") !== "") {
                // Block holds text too: the cursor can already go after the image.
                if (last.lastChild && last.lastChild.nodeType === 3) {
                    return;
                }
            }
            const p = editable.ownerDocument.createElement("p");
            p.appendChild(editable.ownerDocument.createElement("br"));
            editable.appendChild(p);
            this.dependencies.history.addStep();
        } catch (e) {
            console.warn("Could not add a line after the image:", e);
        }
    }

    _getTargetBlock() {
        try {
            const selData = this.dependencies.selection?.getSelectionData?.();
            const anchorNode = selData?.editableSelection?.anchorNode || selData?.deepEditableSelection?.anchorNode;
            if (anchorNode && this.editable) {
                let curr = anchorNode.nodeType === Node.ELEMENT_NODE ? anchorNode : anchorNode.parentElement;
                while (curr && curr.parentElement && curr.parentElement !== this.editable) {
                    curr = curr.parentElement;
                }
                if (curr && curr.parentElement === this.editable) {
                    return curr;
                }
            }
        } catch (e) {
            console.warn("Could not get target block from selection:", e);
        }
        return null;
    }
}

// ── Patch TextDirectionPlugin for empty line support (Item 1) ─────
import { patch } from "@web/core/utils/patch";
import { TextDirectionPlugin } from "@html_editor/main/text_direction_plugin";
import { closestBlock } from "@html_editor/utils/blocks";
import { closestElement } from "@html_editor/utils/dom_traversal";
import { isContentEditable, isTextNode } from "@html_editor/utils/dom_info";

try {
    patch(TextDirectionPlugin.prototype, {
        switchDirection() {
            const selection = this.dependencies.split.splitSelection();
            const targetedTextNodes = [
                selection?.anchorNode,
                ...this.dependencies.selection.getTargetedNodes(),
            ].filter((n) => n && isTextNode(n) && isContentEditable(n) && n.nodeValue.trim().length);

            const blocks = new Set(
                targetedTextNodes.map(
                    (textNode) =>
                        closestElement(textNode, "ul,ol") ||
                        closestElement(textNode, "[data-embedded='toggleBlock']") ||
                        closestBlock(textNode)
                )
            );

            // Empty line / empty block fallback:
            let isEmptyLineFallback = false;
            if (blocks.size === 0) {
                let anchor = selection?.anchorNode;
                if (!anchor || !this.editable.contains(anchor)) {
                    const domSel = window.getSelection();
                    if (domSel && domSel.anchorNode && this.editable.contains(domSel.anchorNode)) {
                        anchor = domSel.anchorNode;
                    }
                }
                if (anchor) {
                    if (anchor === this.editable) {
                        const offset = selection?.anchorOffset ?? window.getSelection()?.anchorOffset ?? 0;
                        anchor = this.editable.childNodes[offset] || this.editable.firstElementChild;
                    }
                    if (anchor) {
                        const targetBlock =
                            closestElement(anchor, "ul,ol") ||
                            closestElement(anchor, "[data-embedded='toggleBlock']") ||
                            closestBlock(anchor);
                        if (targetBlock && targetBlock !== this.editable && this.editable.contains(targetBlock)) {
                            blocks.add(targetBlock);
                            isEmptyLineFallback = true;
                        }
                    }
                }
            }

            if (blocks.size === 0) {
                return;
            }

            for (const block of blocks) {
                for (const node of block.querySelectorAll("ul,ol")) {
                    blocks.add(node);
                }
            }

            // Determine whether to switch to RTL or LTR
            let shouldApplyStyle;
            if (isEmptyLineFallback) {
                const isAnyRtl = Array.from(blocks).some(
                    (b) => b.getAttribute("dir") === "rtl" || getComputedStyle(b).direction === "rtl"
                );
                shouldApplyStyle = !isAnyRtl;
            } else {
                shouldApplyStyle = !this.dependencies.format.isSelectionFormat("switchDirection");
            }

            for (const block of blocks) {
                if (!shouldApplyStyle) {
                    block.removeAttribute("dir");
                    block.style.setProperty("text-align", "left");
                } else {
                    block.setAttribute("dir", this.direction === "ltr" ? "rtl" : "ltr");
                    block.style.setProperty("text-align", this.direction === "ltr" ? "right" : "left");
                }
            }

            for (const element of blocks) {
                const style = getComputedStyle(element);
                if (style.direction === "ltr" && style.textAlign === "right") {
                    element.style.setProperty("text-align", "left");
                } else if (style.direction === "rtl" && style.textAlign === "left") {
                    element.style.setProperty("text-align", "right");
                }
            }
            this.dependencies.history.addStep();
        },
    });
} catch (e) {
    console.warn("Could not patch TextDirectionPlugin", e);
}

