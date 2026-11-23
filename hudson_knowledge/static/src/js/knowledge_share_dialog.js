/** @odoo-module **/
/**
 * Share Settings dialog and Move To dialog of the Knowledge app
 * (Odoo Online style). All changes go through server methods that check
 * the permission of the current user:
 *   get_share_data, action_share_search_users, action_share_invite,
 *   action_share_set_member_permission, action_share_remove_member,
 *   action_share_set_general_access, action_share_set_published,
 *   get_move_targets
 */
import { Component, onWillStart, proxy, useProps, useListener } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";

const ARTICLE_MODEL = "knowledge.management.article";

export const PERMISSION_LABELS = {
    none: _t("No Access"),
    read: _t("Can Read"),
    write: _t("Can Edit"),
};

export class KnowledgeShareDialog extends Component {
    static template = "hudson_knowledge.KnowledgeShareDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.permissionLabels = PERMISSION_LABELS;
        this.state = proxy({
            data: null,
            openMenu: false, // "general" | partner_id
            busy: false,
        });
        this.dialog = useService("dialog");
        onWillStart(() => this.load());
        useListener(document, "click", (ev) => {
            if (!ev.target.closest?.(".o_knowledge_share_menu, .o_knowledge_share_menu_toggle")) {
                this.state.openMenu = false;
            }
        });
    }

    get title() {
        const d = this.state.data;
        return d ? _t("Share Settings for %(icon)s %(name)s", { icon: d.icon, name: d.name }) : _t("Share Settings");
    }

    get canEdit() {
        return Boolean(this.state.data?.can_edit);
    }

    get generalAccessLabel() {
        const d = this.state.data;
        if (!d) return "";
        if (d.visibility === "workspace") {
            return PERMISSION_LABELS[d.internal_permission];
        }
        return _t("Members only");
    }

    get generalAccessHelp() {
        const d = this.state.data;
        if (!d) return "";
        if (d.visibility === "workspace") {
            return _t("All internal users");
        }
        if (d.visibility === "private") {
            return _t("Only you");
        }
        return _t("Only the people below");
    }

    async load() {
        this.state.data = await this.orm.call(ARTICLE_MODEL, "get_share_data", [[this.props.articleId]]);
    }

    async _run(method, args) {
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            const before = this.state.data;
            this.state.data = await this.orm.call(ARTICLE_MODEL, method, [[this.props.articleId], ...args]);
            this.state.openMenu = false;
            if (this.props.onChanged) {
                await this.props.onChanged(this.state.data, before);
            }
        } finally {
            this.state.busy = false;
        }
    }

    // ── Share to web ─────────────────────────────────────────────
    async onTogglePublished(ev) {
        await this._run("action_share_set_published", [ev.target.checked]);
    }

    async onCopyLink() {
        try {
            await browser.navigator.clipboard.writeText(this.state.data.public_url);
            this.notification.add(_t("Link copied to clipboard."), { type: "success" });
        } catch {
            this.notification.add(this.state.data.public_url, { title: _t("Public link") });
        }
    }

    // ── General access ───────────────────────────────────────────
    toggleMenu(key) {
        this.state.openMenu = this.state.openMenu === key ? false : key;
    }

    async onSetGeneralAccess(value) {
        await this._run("action_share_set_general_access", [value]);
    }

    // ── Add people (opens the Share dialog) ──────────────────────
    openShareDialog() {
        this.dialog.add(KnowledgeShareInviteDialog, {
            articleId: this.props.articleId,
            onShared: async (data) => {
                const before = this.state.data;
                this.state.data = data;
                if (this.props.onChanged) {
                    await this.props.onChanged(data, before);
                }
            },
        });
    }

    // ── Members ──────────────────────────────────────────────────
    async onSetMemberPermission(member, permission) {
        if (member.permission === permission && !member.inherited) {
            this.state.openMenu = false;
            return;
        }
        await this._run("action_share_set_member_permission", [member.partner_id, permission]);
    }

    async onRemoveMember(member) {
        await this._run("action_share_remove_member", [member.partner_id]);
    }

    memberInitial(member) {
        return (member.name || "?").trim().charAt(0).toUpperCase();
    }
}

// ─────────────────────────────────────────────────────────────────
// Share dialog (add people): permission, recipients, extra comment
// ─────────────────────────────────────────────────────────────────
export class KnowledgeShareInviteDialog extends Component {
    static template = "hudson_knowledge.KnowledgeShareInviteDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            permission: "write",
            search: "",
            suggestions: [],
            selected: [],
            showSuggestions: false,
            message: "",
            busy: false,
        });
        this._searchTimer = null;
        useListener(document, "click", (ev) => {
            if (!ev.target.closest?.(".o_knowledge_share_invite")) {
                this.state.showSuggestions = false;
            }
        });
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.showSuggestions = true;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.fetchSuggestions(), 200);
    }

    onSearchFocus() {
        this.state.showSuggestions = true;
        this.fetchSuggestions();
    }

    async fetchSuggestions() {
        const selectedIds = this.state.selected.map((s) => s.partner_id);
        const res = await this.orm.call(ARTICLE_MODEL, "action_share_search_users", [
            [this.props.articleId],
            this.state.search,
        ]);
        this.state.suggestions = res.filter((r) => !selectedIds.includes(r.partner_id));
    }

    onPickSuggestion(suggestion) {
        this.state.selected.push(suggestion);
        this.state.search = "";
        this.state.suggestions = this.state.suggestions.filter((s) => s.partner_id !== suggestion.partner_id);
        this.state.showSuggestions = false;
    }

    onUnpick(partnerId) {
        this.state.selected = this.state.selected.filter((s) => s.partner_id !== partnerId);
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            if (this.state.suggestions.length && this.state.search) {
                this.onPickSuggestion(this.state.suggestions[0]);
            }
        } else if (ev.key === "Backspace" && !this.state.search && this.state.selected.length) {
            this.state.selected.pop();
        }
    }

    async onShare() {
        if (this.state.busy) return;
        if (!this.state.selected.length && this.state.search && this.state.suggestions.length) {
            this.onPickSuggestion(this.state.suggestions[0]);
        }
        if (!this.state.selected.length) {
            this.notification.add(_t("Select at least one recipient."), { type: "warning" });
            return;
        }
        this.state.busy = true;
        try {
            const data = await this.orm.call(ARTICLE_MODEL, "action_share_invite", [
                [this.props.articleId],
                this.state.selected.map((s) => s.partner_id),
                this.state.permission,
                this.state.message,
            ]);
            await this.props.onShared(data);
            this.props.close();
        } finally {
            this.state.busy = false;
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// Move To dialog
// ─────────────────────────────────────────────────────────────────
export class KnowledgeMoveDialog extends Component {
    static template = "hudson_knowledge.KnowledgeMoveDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ search: "", targets: [], selected: null });
        this._timer = null;
        onWillStart(() => this.fetch());
    }

    get sections() {
        return [
            { key: "workspace", label: _t("Workspace"), icon: "business" },
            { key: "private", label: _t("Private"), icon: "lock" },
        ];
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this._timer);
        this._timer = setTimeout(() => this.fetch(), 200);
    }

    async fetch() {
        this.state.targets = await this.orm.call(ARTICLE_MODEL, "get_move_targets", [
            [this.props.article.id],
            this.state.search,
        ]);
    }

    select(target) {
        this.state.selected = target;
    }

    isSelected(target) {
        const s = this.state.selected;
        return Boolean(s && s.kind === target.kind && s.id === target.id);
    }

    async onConfirm() {
        if (!this.state.selected) return;
        await this.props.onMove(this.state.selected);
        this.props.close();
    }
}
