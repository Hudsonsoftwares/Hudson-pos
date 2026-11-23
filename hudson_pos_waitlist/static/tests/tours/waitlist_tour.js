import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import { registry } from "@web/core/registry";

const panel = ".o_hudson_waitlist_panel";
const entry = (token) => `${panel} .o_hw_entry:contains("${token}")`;

registry.category("web_tour.tours").add("hudson_pos_waitlist_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            {
                content: "Waitlist button shows the active count",
                trigger: ".o_hw_navbar_btn .o_hw_badge:contains(2)",
            },
            {
                content: "Open the waitlist panel",
                trigger: ".o_hw_navbar_btn",
                run: "click",
            },
            {
                content: "First guest with details and estimated wait",
                trigger: `${entry("W-001")}:contains("Ada Lovelace"):contains("Main Floor"):contains("Private table"):contains("10 min")`,
            },
            {
                content: "Second guest: same flat average wait (10 min, not 20)",
                trigger: `${entry("W-002")}:contains("Grace Hopper"):contains("10 min")`,
            },
            {
                content: "Waiting guest offers Seat Guest directly; no Call step exists",
                trigger: `${entry("W-001")}:has(button:contains("Seat Guest")):has(button:contains("Mark No Show"))`,
                run: () => {
                    const panelEl = document.querySelector(panel);
                    if (/Call Guest|Called/.test(panelEl.textContent)) {
                        throw new Error("Call / Called is still shown in the POS waitlist");
                    }
                },
            },
            {
                content: "Seat Guest opens the table picker",
                trigger: `${entry("W-001")} button:contains("Seat Guest")`,
                run: "click",
            },
            {
                content: "Pick free table 4",
                trigger: `.o_hudson_waitlist_tables .o_hw_table[data-table="4"]`,
                run: "click",
            },
            {
                content: "Seat without leaving the waitlist",
                trigger: `.modal:has(.o_hudson_waitlist_tables) .o_hw_seat_only:enabled`,
                run: "click",
            },
            {
                content: "Seated guest leaves the list, badge drops to 1",
                trigger: `.o_hw_navbar_btn .o_hw_badge:contains(1)`,
            },
            {
                content: "Cancel the remaining guest",
                trigger: `${entry("W-002")} button:contains("Cancel")`,
                run: "click",
            },
            Dialog.confirm("Cancel"),
            {
                content: "Queue is empty",
                trigger: `${panel} .o_hw_empty`,
            },
        ].flat(),
});

import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as FloorScreen from "@pos_restaurant/../tests/tours/utils/floor_screen_util";

registry.category("web_tour.tours").add("hudson_pos_waitlist_seat_open_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            {
                content: "Open the waitlist panel",
                trigger: ".o_hw_navbar_btn",
                run: "click",
            },
            {
                content: "Seat the waiting guest",
                trigger: `${entry("W-001")} button:contains("Seat Guest")`,
                run: "click",
            },
            {
                content: "Table 5 is offered (free)",
                trigger: `.o_hudson_waitlist_tables .o_hw_table[data-table="5"]`,
                run: "click",
            },
            {
                content: "Seat and open the table",
                trigger: `.modal:has(.o_hudson_waitlist_tables) .o_hw_seat_open:enabled`,
                run: "click",
            },
            // Normal restaurant flow from here on.
            ProductScreen.isShown(),
            ProductScreen.clickDisplayedProduct("Coca-Cola", true),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),
            FloorScreen.orderCountSyncedInTableIs("5", "1"),
        ].flat(),
});

// ---------------------------------------------------------------------------
// Preferred floor in the picker, then the complete normal POS flow on the table:
// Seat & Open -> guest count -> add product -> pay -> next order.
// ---------------------------------------------------------------------------
import * as PaymentScreen from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as FeedbackScreen from "@point_of_sale/../tests/pos/tours/utils/feedback_screen_util";
import * as RestaurantProductScreen from "@pos_restaurant/../tests/tours/utils/product_screen_util";

const picker = ".o_hudson_waitlist_tables";

registry.category("web_tour.tours").add("hudson_pos_waitlist_floor_full_flow_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            { content: "Open the waitlist panel", trigger: ".o_hw_navbar_btn", run: "click" },
            {
                content: "Guest shows the preferred floor, not Indoor/Outdoor",
                trigger: `${entry("W-001")}:contains("Second Floor"):contains("Private table"):not(:contains("Indoor"))`,
            },
            {
                content: "Seat the waiting guest",
                trigger: `${entry("W-001")} button:contains("Seat Guest")`,
                run: "click",
            },
            {
                content: "Picker opens on the preferred floor, marked as preferred",
                trigger: `.o_hw_floor_tabs button.active.o_hw_floor_preferred[data-floor="Second Floor"]:contains("Preferred")`,
            },
            {
                content: "Second Floor tables are suitable for the party of 3",
                trigger: `${picker} .o_hw_table[data-table="3"][data-status="match"]:contains("Suitable")`,
                run: () => {
                    if (!document.querySelector(`${picker} .o_hw_table[data-table="1"][data-status="match"]`)) {
                        throw new Error("table 1 (Second Floor) should be suitable");
                    }
                    if (!document.querySelector(".o_hw_seat_open").disabled) {
                        throw new Error("Seat & Open enabled before a table is chosen: no auto-assignment");
                    }
                },
            },
            {
                content: "Look at the other floor",
                trigger: `.o_hw_floor_tabs button[data-floor="Main Floor"]`,
                run: "click",
            },
            {
                content: "Main Floor tables are shown for information only",
                trigger: `${picker} .o_hw_floor_note`,
                run: () => {
                    const tables = document.querySelectorAll(`${picker} .o_hw_table`);
                    if (!tables.length) {
                        throw new Error("Main Floor tables are not shown");
                    }
                    for (const table of tables) {
                        if (!table.disabled || table.dataset.status !== "other_floor") {
                            throw new Error(`table ${table.dataset.table} on another floor is pickable`);
                        }
                    }
                },
            },
            {
                content: "Back to the preferred floor",
                trigger: `.o_hw_floor_tabs button[data-floor="Second Floor"]`,
                run: "click",
            },
            {
                content: "Host picks table 3",
                trigger: `${picker} .o_hw_table[data-table="3"]:enabled`,
                run: "click",
            },
            {
                content: "Seat and open the table",
                trigger: `.modal:has(${picker}) .o_hw_seat_open:enabled`,
                run: "click",
            },
            // Standard restaurant order flow from here on.
            ProductScreen.isShown(),
            // Guest count = party size is asserted on the saved pos.order (customer_count == 3).
            ProductScreen.clickDisplayedProduct("Coca-Cola", true),
            // Send to kitchen exactly like any table order.
            RestaurantProductScreen.clickOrderButton(),
            Chrome.closePrintingWarning(),
            FloorScreen.clickFloor("Second Floor"),
            FloorScreen.clickTable("3"),
            RestaurantProductScreen.orderlinesHaveNoChange(),
            ProductScreen.clickPayButton(false),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            FeedbackScreen.clickNextOrder(),
        ].flat(),
});

// ---------------------------------------------------------------------------
// End-to-end: guest phone + this POS + "another terminal".
// The phone and the other terminal act through plain HTTP, never through this POS's
// UI, so every change they make can only reach this screen over the bus.
// ---------------------------------------------------------------------------
const E2E_TOKEN = "e2eWaitlistToken0001";

async function otherTerminal(method, args) {
    const response = await fetch("/web/dataset/call_kw", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: { model: "pos.waitlist.entry", method, args, kwargs: {} },
        }),
    });
    const data = await response.json();
    if (data.error) {
        throw new Error(`${method} failed: ${JSON.stringify(data.error)}`);
    }
    return data.result;
}

async function entryId(token) {
    const queue = await otherTerminal("get_pos_queue", [odoo.pos_config_id]);
    const found = queue.entries.find((e) => e.token === token);
    if (!found) {
        throw new Error(`${token} is not in the active queue`);
    }
    return found;
}

async function tableId(number) {
    const response = await fetch("/web/dataset/call_kw", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: {
                model: "restaurant.table",
                method: "search_read",
                args: [
                    [
                        ["table_number", "=", number],
                        ["floor_id.pos_config_ids", "in", [odoo.pos_config_id]],
                    ],
                    ["id"],
                ],
                kwargs: {},
            },
        }),
    });
    return (await response.json()).result[0].id;
}

registry.category("web_tour.tours").add("hudson_pos_waitlist_e2e_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            {
                content: "Guest who joined before the POS opened is loaded",
                trigger: ".o_hw_navbar_btn .o_hw_badge:contains(1)",
            },
            {
                // Same public form POST a phone sends. The session cookie only tells the
                // multi-database test server which database to use (phones are routed by the
                // QR token, which an uncommitted test database cannot provide).
                content: "A second guest joins through the public join form",
                trigger: ".o_hw_navbar_btn",
                run: async () => {
                    const body = new URLSearchParams({
                        guest_name: "Grace Hopper",
                        phone: "+1 555 010 0002",
                        party_size: "3",
                        share_table: "share",
                    });
                    const r = await fetch(`/waitlist/join/${E2E_TOKEN}`, {
                        method: "POST",
                        body,
                        redirect: "manual",
                    });
                    // 303 to the status page comes back as an opaque redirect (status 0).
                    if (r.type !== "opaqueredirect" && !r.ok) {
                        throw new Error(`join failed: ${r.status}`);
                    }
                },
            },
            {
                content: "POS receives the new guest live: badge 2",
                trigger: ".o_hw_navbar_btn .o_hw_badge:contains(2)",
            },
            {
                content: "Open the waitlist",
                trigger: ".o_hw_navbar_btn",
                run: "click",
            },
            {
                content: "Phone guest is listed with their details",
                trigger: `${entry("W-002")}:contains("Grace Hopper"):contains("Any Floor"):contains("Can share")`,
            },
            {
                content: "Host seats W-001",
                trigger: `${entry("W-001")} button:contains("Seat Guest")`,
                run: "click",
            },
            {
                content: "Pick table 4",
                trigger: `.o_hudson_waitlist_tables .o_hw_table[data-table="4"]`,
                run: "click",
            },
            {
                content: "Seat only",
                trigger: `.modal:has(.o_hudson_waitlist_tables) .o_hw_seat_only:enabled`,
                run: "click",
            },
            {
                content: "W-001 left the list: badge 1",
                trigger: ".o_hw_navbar_btn .o_hw_badge:contains(1)",
            },
            {
                // Run from an element inside the open panel (the navbar sits behind its backdrop).
                content: "Other terminal: table 4 is refused, table 2 works",
                trigger: `${panel} .o_hw_entry:contains("W-002")`,
                run: async () => {
                    // Other terminal tries the table that was just given away.
                    const guest = await entryId("W-002");
                    const taken = await otherTerminal("pos_seat_guest", [
                        odoo.pos_config_id, guest.id, "waiting", await tableId(4),
                    ]);
                    if (taken.ok || taken.state !== "waiting" || !taken.message.includes("W-001")) {
                        throw new Error(`table 4 was given twice: ${JSON.stringify(taken)}`);
                    }
                    const seated = await otherTerminal("pos_seat_guest", [
                        odoo.pos_config_id, guest.id, "waiting", await tableId(2),
                    ]);
                    if (!seated.ok) {
                        throw new Error(seated.message);
                    }
                },
            },
            {
                content: "Other terminal seated W-002: the list empties live",
                trigger: `${panel} .o_hw_empty`,
            },
            {
                content: "Badge is gone",
                trigger: ".o_hw_navbar_btn:not(:has(.o_hw_badge))",
            },
        ].flat(),
});

// ---------------------------------------------------------------------------
// UI edge cases and regression: counts, layout, refresh, picker, races.
// ---------------------------------------------------------------------------
function badgeIs(count) {
    return {
        content: `Badge shows ${count}`,
        trigger: `.o_hw_navbar_btn .o_hw_badge:contains(${count})`,
    };
}

function confirmAction(token, label) {
    return [
        {
            content: `${label} ${token}`,
            trigger: `${entry(token)} button:contains("${label}")`,
            run: "click",
        },
        Dialog.confirm(label),
    ];
}

function assertNoOverflow(selector) {
    for (const el of document.querySelectorAll(selector)) {
        if (el.scrollWidth > el.clientWidth + 1) {
            throw new Error(`${selector} overflows: ${el.scrollWidth} > ${el.clientWidth}`);
        }
    }
}

async function seatFromOtherTerminal(token, tableNumber) {
    const guest = await entryId(token);
    const seated = await otherTerminal("pos_seat_guest", [
        odoo.pos_config_id, guest.id, "waiting", await tableId(tableNumber),
    ]);
    if (!seated.ok) {
        throw new Error(seated.message);
    }
}

registry.category("web_tour.tours").add("hudson_pos_waitlist_ui_edge_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            badgeIs(5),
            {
                content: "Join from the public form",
                trigger: ".o_hw_navbar_btn",
                run: async () => {
                    const body = new URLSearchParams({
                        guest_name: "Phone Joiner",
                        phone: "+1 555 030 0006",
                        party_size: "2",
                        preferred_floor: "any",
                        share_table: "private",
                    });
                    await fetch(`/waitlist/join/${E2E_TOKEN}`, { method: "POST", body, redirect: "manual" });
                },
            },
            badgeIs(6),
            { content: "Open the waitlist", trigger: ".o_hw_navbar_btn", run: "click" },

            // Layout: long name, party of 50, many tags.
            {
                content: "Long name, big party and all tags render inside the card",
                trigger: `${entry("W-001")}:contains("50"):contains("Anniversary")`,
                run: () => {
                    const card = [...document.querySelectorAll(".o_hw_entry")].find((e) =>
                        e.textContent.includes("W-001")
                    );
                    const tags = card.querySelectorAll(".o_hw_guest .badge.text-bg-secondary");
                    if (tags.length !== 6) {
                        throw new Error(`expected 6 tags, got ${tags.length}`);
                    }
                    assertNoOverflow(".o_hw_entry");
                    assertNoOverflow(".o_hudson_waitlist_panel");
                    const panelBox = document.querySelector(".o_hudson_waitlist_panel").getBoundingClientRect();
                    for (const el of card.querySelectorAll(".badge, .btn, .o_hw_times")) {
                        if (el.getBoundingClientRect().right > panelBox.right + 1) {
                            throw new Error(`"${el.textContent.trim()}" sticks out of the panel`);
                        }
                    }
                },
            },

            // Waiting guests are seated directly: Seat Guest, Cancel, Mark Left, Mark No Show.
            {
                content: "Waiting guest: Waiting badge and every host action, no Call",
                trigger: `${entry("W-002")}:contains("Waiting"):has(button:contains("Seat Guest")):has(button:contains("Mark No Show"))`,
                run: () => {
                    if (document.querySelector(`${panel}`).textContent.includes("Call")) {
                        throw new Error("Call / Called is still shown");
                    }
                },
            },

            // Count after Cancel / Left / No Show.
            ...confirmAction("W-003", "Cancel"),
            badgeIs(5),
            ...confirmAction("W-004", "Mark Left"),
            badgeIs(4),
            ...confirmAction("W-005", "Mark No Show"),
            badgeIs(3),

            // Refresh the POS: no duplicates, state kept.
            {
                content: "Reload the POS",
                trigger: `${entry("W-006")}`,
                run: () => window.location.reload(),
                expectUnloadPage: true,
            },
            badgeIs(3),
            { content: "Reopen the waitlist", trigger: ".o_hw_navbar_btn", run: "click" },
            {
                content: "Exactly the 3 active guests, once each",
                trigger: `${entry("W-006")}`,
                run: () => {
                    const tokens = [...document.querySelectorAll(".o_hw_entry .o_hw_token .fs-4")].map(
                        (e) => e.textContent.trim()
                    );
                    if (tokens.join(",") !== "W-001,W-002,W-006") {
                        throw new Error(`unexpected list after reload: ${tokens.join(",")}`);
                    }
                },
            },

            // Seat picker.
            {
                content: "Seat W-001",
                trigger: `${entry("W-001")} button:contains("Seat Guest")`,
                run: "click",
            },
            {
                content: "Both POS floors are offered",
                trigger: `.o_hw_floor_tabs:has(button:contains("Main Floor")):has(button:contains("Second Floor"))`,
            },
            {
                content: "Occupied table 5 shown but not pickable; free tables marked too small for 50",
                trigger: `.o_hudson_waitlist_tables .o_hw_table[data-table="4"].o_hw_table_small:contains("Too small")`,
                run: () => {
                    const t5 = document.querySelector('.o_hudson_waitlist_tables .o_hw_table[data-table="5"]');
                    if (!t5 || !t5.disabled || t5.dataset.status !== "busy" || !t5.textContent.includes("Occupied")) {
                        throw new Error("occupied table 5 must be shown as Occupied and disabled");
                    }
                    if (!document.querySelector(".o_hw_seat_only").disabled) {
                        throw new Error("confirm enabled before choosing a table");
                    }
                },
            },
            {
                content: "Close the picker without seating",
                trigger: `.modal:has(.o_hudson_waitlist_tables) .modal-footer button:contains("Back")`,
                run: "click",
            },
            {
                content: "Guest is still waiting",
                trigger: `${panel} .o_hw_entry:contains("W-001"):contains("Waiting")`,
            },
            badgeIs(3),
            {
                content: "Seat W-001 again",
                trigger: `${entry("W-001")} button:contains("Seat Guest")`,
                run: "click",
            },
            {
                content: "Pick table 4",
                trigger: `.o_hudson_waitlist_tables .o_hw_table[data-table="4"]`,
                run: "click",
            },
            {
                content: "Meanwhile another terminal gives table 4 to W-006",
                trigger: `.o_hudson_waitlist_tables .o_hw_table.active[data-table="4"]`,
                run: async () => seatFromOtherTerminal("W-006", 4),
            },
            {
                content: "Confirm the now-taken table",
                trigger: `.modal:has(.o_hudson_waitlist_tables) .o_hw_seat_only:enabled`,
                run: "click",
            },
            {
                content: "Clear error in the picker, table 4 now occupied, guest still pickable",
                trigger: `.o_hw_seat_message:contains("W-006"):contains("Choose another table")`,
                run: () => {
                    const t4 = document.querySelector('.o_hudson_waitlist_tables .o_hw_table[data-table="4"]');
                    if (t4 && !t4.disabled) {
                        throw new Error("taken table 4 still offered");
                    }
                    if (!document.querySelector(".o_hw_seat_only").disabled) {
                        throw new Error("confirm still enabled without a table");
                    }
                },
            },
            badgeIs(2),
            {
                content: "Pick table 2 on the second try",
                trigger: `.o_hudson_waitlist_tables .o_hw_table[data-table="2"]`,
                run: "click",
            },
            {
                content: "Double-click Seat Only",
                trigger: `.modal:has(.o_hudson_waitlist_tables) .o_hw_seat_only:enabled`,
                run: () => {
                    const button = document.querySelector(".o_hw_seat_only");
                    button.click();
                    button.click();
                },
            },
            badgeIs(1),
            {
                content: "W-001 left the list; only W-002 remains",
                trigger: `${panel}:not(:has(.o_hw_entry:contains("W-001"))) .o_hw_entry:contains("W-002")`,
            },
            ...confirmAction("W-002", "Cancel"),
            {
                content: "Empty state",
                trigger: `${panel} .o_hw_empty:contains("No guests are waiting")`,
            },
            {
                content: "Badge hidden when empty",
                trigger: ".o_hw_navbar_btn:not(:has(.o_hw_badge))",
            },
            {
                content: "No duplicate-action warning was raised by the double click",
                trigger: `body:not(:has(.o_notification:contains("another terminal")))`,
            },
        ].flat(),
});
