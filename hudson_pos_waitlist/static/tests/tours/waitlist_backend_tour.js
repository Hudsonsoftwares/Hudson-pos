import { registry } from "@web/core/registry";

// Backend Waitlist menu follows changes made elsewhere (POS terminal / another tab),
// without any reload. "Elsewhere" = plain RPCs, so the update can only arrive over the bus.

async function rpc(model, method, args) {
    const response = await fetch("/web/dataset/call_kw", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: { model, method, args, kwargs: {} },
        }),
    });
    const data = await response.json();
    if (data.error) {
        throw new Error(`${method} failed: ${JSON.stringify(data.error)}`);
    }
    return data.result;
}

async function entry(token) {
    const [found] = await rpc("pos.waitlist.entry", "search_read", [
        [["token", "=", token]],
        ["id", "config_id", "state"],
    ]);
    return found;
}

async function posAction(token, expected, next) {
    const e = await entry(token);
    const result = await rpc("pos.waitlist.entry", "pos_change_state", [
        e.config_id[0], e.id, expected, next,
    ]);
    if (!result.ok) {
        throw new Error(result.message);
    }
}

const row = (token) => `.o_list_view .o_data_row:has(td[name="token"]:contains("${token}"))`;
const NO_RELOAD = "__hwNoReload";

registry.category("web_tour.tours").add("hudson_pos_waitlist_backend_sync_tour", {
    steps: () => [
        {
            content: "List shows both guests as Waiting",
            trigger: `${row("W-001")} td[name="state"]:contains("Waiting")`,
            run: () => {
                window[NO_RELOAD] = true; // lost on any full page reload
            },
        },
        {
            content: "No Called status anywhere in the list",
            trigger: `${row("W-002")} td[name="state"]:contains("Waiting")`,
            run: () => {
                if (document.querySelector(".o_list_view").textContent.includes("Called")) {
                    throw new Error("Called is still displayed");
                }
            },
        },
        {
            content: "POS cancels W-002",
            trigger: `${row("W-002")}`,
            run: () => posAction("W-002", "waiting", "cancelled"),
        },
        {
            content: "Cancelled guest leaves the Active list without reloading",
            trigger: `.o_list_view:not(:has(.o_data_row td[name="token"]:contains("W-002"))) .o_data_row td[name="token"]:contains("W-001")`,
            run: () => {
                if (!window[NO_RELOAD]) {
                    throw new Error("the page was reloaded");
                }
            },
        },
        {
            content: "Open W-001",
            trigger: `${row("W-001")} td[name="guest_name"]`,
            run: "click",
        },
        {
            content: "Form shows Waiting; the statusbar is Waiting -> Seated only",
            trigger: `.o_form_view:has(.o_statusbar_status .o_arrow_button_current:contains("Waiting"))`,
            run: () => {
                const steps = [...document.querySelectorAll(".o_form_view .o_statusbar_status .o_arrow_button")]
                    .map((b) => b.textContent.trim())
                    .filter(Boolean);
                if (steps.includes("Called")) {
                    throw new Error(`Called still in the statusbar: ${steps.join(", ")}`);
                }
            },
        },
        {
            content: "POS seats W-001 directly from Waiting (no table on this POS)",
            trigger: ".o_form_view",
            run: () => posAction("W-001", "waiting", "seated"),
        },
        {
            content: "Form follows: Seated, without reload",
            // The current status button is disabled: anchor on the form that contains it.
            trigger: `.o_form_view:has(.o_statusbar_status .o_arrow_button_current:contains("Seated"))`,
            run: () => {
                if (!window[NO_RELOAD]) {
                    throw new Error("the page was reloaded");
                }
            },
        },
    ],
});
