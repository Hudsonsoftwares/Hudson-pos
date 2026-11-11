/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog, deleteConfirmationMessage } from "@web/core/confirmation_dialog/confirmation_dialog";

window.__hds_rpc = rpc;

let globalActionService = null;
let globalOrmService = null;
let globalNotificationService = null;
let globalDialogService = null;

// Register service to capture active Odoo ActionService, ORM, Notification, and Dialog
const hdsDashboardNavService = {
    dependencies: ["action", "orm", "notification", "dialog"],
    start(env, { action, orm, notification, dialog }) {
        globalActionService = action;
        globalOrmService = orm;
        globalNotificationService = notification;
        globalDialogService = dialog;
        window.__hds_action = action;
        window.__hds_orm = orm;
        window.__hds_notification = notification;
        window.__hds_dialog = dialog;
        console.log("[HDS Dashboard] Navigation services registered successfully.");
    },
};

registry.category("services").add("hds_dashboard_nav_service", hdsDashboardNavService);

(function () {
    "use strict";

    console.log("[HDS Dashboard Navigation] Script active.");

    function getActionService() {
        if (window.__hds_action) return window.__hds_action;
        if (globalActionService) return globalActionService;
        const selectors = [".o_web_client", ".o_action_manager", ".o_main_navbar", ".o_content", "[class*='o_']"];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el && el.__owl__?.component?.env?.services?.action) {
                globalActionService = el.__owl__.component.env.services.action;
                window.__hds_action = globalActionService;
                return globalActionService;
            }
        }
        if (window.odoo?.__WOWL_DEBUG__?.root?.env?.services?.action) {
            globalActionService = window.odoo.__WOWL_DEBUG__.root.env.services.action;
            window.__hds_action = globalActionService;
            return globalActionService;
        }
        return null;
    }

    const ACTION_URL_MAP = {
        total_payroll_cost: "/odoo/action-273",
        total_net_pay: "/odoo/action-273",
        active_employee_count: "/odoo/action-197",
        tds_this_month: "/odoo/action-273",
        tds_withholding: "/odoo/action-273",
        pending_actions: "/odoo/action-687",
        missing_pan: "/odoo/action-687",
        missing_bank: "/odoo/action-688",
        pending_declarations: "/odoo/action-689",
        attendance_exceptions: "/odoo/action-690",
        new_joiners: "/odoo/action-691",
        final_settlements_due: "/odoo/action-197",
        pan_health: "/odoo/action-687",
        bank_health: "/odoo/action-688",
        aadhaar_health: "/odoo/action-197",
        contact_health: "/odoo/action-197",
        epf_status: "/odoo/action-694",
        esic_status: "/odoo/action-695",
        lwf_status: "/odoo/action-197",
        readiness_status: "/odoo/action-197",
        epf_liability: "/odoo/action-273",
        esic_liability: "/odoo/action-273",
        pt_liability: "/odoo/action-273",
        old_regime: "/odoo/action-692",
        new_regime: "/odoo/action-693",
        tds_ytd: "/odoo/action-566",
    };

    const CARD_ACTIONS = {
        total_payroll_cost: {
            name: "Total Payroll Cost Slips",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        total_net_pay: {
            name: "Net Salary Disbursement",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        active_employee_count: {
            name: "Active Employees",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true]],
        },
        tds_this_month: {
            name: "TDS Withholding Slips",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        tds_withholding: {
            name: "TDS Withholding Slips",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        govt_deposit: {
            name: "Govt Deposit",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", ["done", "paid"]]],
        },
        decl_pending: {
            name: "Declarations Pending Verification",
            res_model: "tds.employee.declaration",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", ["submitted", "proof_submitted", "proof_under_review"]]],
        },
        decl_declared: {
            name: "Declarations Awaiting Proofs",
            res_model: "tds.employee.declaration",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "declared"]],
        },
        decl_draft: {
            name: "Declarations Not Submitted",
            res_model: "tds.employee.declaration",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "draft"]],
        },
        net_breakdown: {
            name: "Net Salary",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", ["done", "paid"]]],
        },
        tds_breakdown: {
            name: "TDS This Month",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", ["done", "paid"]]],
        },
        ctc_breakdown: {
            name: "Total Payroll Cost (CTC)",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", ["done", "paid"]]],
        },
        pending_actions: {
            name: "Employees Requiring Action",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], "|", "|", ["hds_in_pan", "=", false], ["hds_in_pan", "=", ""], ["bank_account_id", "=", false]],
        },
        missing_pan: {
            name: "Employees Missing PAN",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], "|", ["hds_in_pan", "=", false], ["hds_in_pan", "=", ""]],
        },
        missing_bank: {
            name: "Employees Missing Bank Details",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], ["bank_account_id", "=", false]],
        },
        pending_declarations: {
            name: "Pending Tax Declarations",
            res_model: "tds.employee.declaration",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", ["submitted", "proof_submitted", "proof_under_review"]]],
        },
        attendance_exceptions: {
            name: "Payslips to Validate",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", ["draft", "verify"]]],
        },
        new_joiners: {
            name: "New Joiners",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true]],
        },
        exits: {
            name: "Exits",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "in", [true, false]], ["departure_date", "!=", false]],
        },
        final_settlements_due: {
            name: "Exited / Inactive Employees",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", false]],
        },
        pan_health: {
            name: "Employees Missing PAN",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], "|", ["hds_in_pan", "=", false], ["hds_in_pan", "=", ""]],
        },
        bank_health: {
            name: "Employees Missing Bank Details",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], ["bank_account_id", "=", false]],
        },
        aadhaar_health: {
            name: "Employees Missing Aadhaar",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], "|", ["hds_in_aadhaar", "=", false], ["hds_in_aadhaar", "=", ""]],
        },
        contact_health: {
            name: "Employees Missing Emergency Contact",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], "&", "|", ["emergency_contact", "=", false], ["emergency_contact", "=", ""], "|", ["emergency_phone", "=", false], ["emergency_phone", "=", ""]],
        },
        epf_status: {
            name: "Employees Missing EPF UAN",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], ["hds_in_epf_applicable", "=", true], "|", ["hds_in_uan", "=", false], ["hds_in_uan", "=", ""]],
        },
        esic_status: {
            name: "Employees Missing ESIC IP Number",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], ["hds_in_esic_applicable", "=", true], "|", ["hds_in_esic_ip", "=", false], ["hds_in_esic_ip", "=", ""]],
        },
        lwf_status: {
            name: "Employees Missing LWF Registration",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], ["hds_in_lwf_applicable", "=", true]],
        },
        readiness_status: {
            name: "Employees with Statutory Data Errors",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true]],
        },
        epf_liability: {
            name: "EPF Liability Slips",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        esic_liability: {
            name: "Employer ESIC Contribution Slips",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        lwf_liability: {
            name: "Employer LWF Contribution Slips",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        total_employer_statutory: {
            name: "Employer Statutory Contribution Slips",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        pt_liability: {
            name: "Professional Tax Slips",
            res_model: "hr.payslip",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "!=", "cancel"]],
        },
        old_regime: {
            name: "Employees in Old Tax Regime",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], ["hds_in_tax_regime", "=", "old"]],
        },
        new_regime: {
            name: "Employees in New Tax Regime (115BAC)",
            res_model: "hr.employee",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true], ["hds_in_tax_regime", "=", "new"]],
        },
        tds_ytd: {
            name: "TDS Declarations",
            res_model: "tds.employee.declaration",
            views: [[false, "list"], [false, "form"]],
            domain: [],
        },
    };

    // Primary card click: Navigates on current page with breadcrumbs to return
    window.hdsCardClick = function (cardEl, cardType) {
        if (!cardType) return false;

        if (cardEl) {
            document.querySelectorAll(".hds-card-active").forEach(el => el.classList.remove("hds-card-active"));
            cardEl.classList.add("hds-card-active");
        }

        const executeAction = (actionDef) => {
            const actionService = getActionService();
            if (actionService && actionService.doAction) {
                actionService.doAction({
                    type: "ir.actions.act_window",
                    name: actionDef.name,
                    res_model: actionDef.res_model,
                    views: actionDef.views || [[false, "list"], [false, "form"]],
                    domain: actionDef.domain || [],
                    target: actionDef.target || "current",
                }, { clearBreadcrumbs: false });
            } else {
                console.warn("[HDS Dashboard] ActionService not available yet for card click, retrying...");
                setTimeout(() => {
                    const retryService = getActionService();
                    if (retryService && retryService.doAction) {
                        retryService.doAction({
                            type: "ir.actions.act_window",
                            name: actionDef.name,
                            res_model: actionDef.res_model,
                            views: actionDef.views || [[false, "list"], [false, "form"]],
                            domain: actionDef.domain || [],
                            target: actionDef.target || "current",
                        }, { clearBreadcrumbs: false });
                    }
                }, 100);
            }
        };

        function fallbackLocal() {
            const baseDef = CARD_ACTIONS[cardType] || {
                name: "Employees",
                res_model: "hr.employee",
                views: [[false, "list"], [false, "form"]],
                domain: [["active", "=", true]],
            };

            const rootEl = (cardEl && cardEl.closest) ? (cardEl.closest(".o_hds_dashboard_root") || cardEl.closest("[data-hds-dashboard-root]")) : document.querySelector(".o_hds_dashboard_root");
            const dateFrom = cardEl?.dataset?.dateFrom || rootEl?.dataset?.dateFrom;
            const dateTo = cardEl?.dataset?.dateTo || rootEl?.dataset?.dateTo;

            let domain = Array.isArray(baseDef.domain) ? [...baseDef.domain] : [];
            if (baseDef.res_model === "hr.payslip" && dateFrom && dateTo) {
                domain.push(["date_from", "<=", dateTo]);
                domain.push(["date_to", ">=", dateFrom]);
            }

            executeAction({
                name: baseDef.name,
                res_model: baseDef.res_model,
                views: baseDef.views,
                domain: domain,
            });
        }

        const rootEl = (cardEl && cardEl.closest) ? (cardEl.closest(".o_hds_dashboard_root") || cardEl.closest("[data-hds-dashboard-root]")) : document.querySelector(".o_hds_dashboard_root");
        const monthSelect = document.querySelector("[name='payroll_month_num'] select, select[name='payroll_month_num']");
        const selectedMonth = (monthSelect && monthSelect.value) ? monthSelect.value : (cardEl?.dataset?.monthNum || rootEl?.dataset?.monthNum);

        const actionService = getActionService();
        if (rpc && actionService) {
            rpc("/web/dataset/call_kw/hds.payroll.dashboard/get_card_action", {
                model: "hds.payroll.dashboard",
                method: "get_card_action",
                args: [],
                kwargs: {
                    card_type: cardType,
                    month_num: selectedMonth,
                    // Period of the clicked element itself (e.g. a past month bar in the trend chart)
                    date_from: cardEl?.dataset?.dateFrom || null,
                    date_to: cardEl?.dataset?.dateTo || null,
                    // Same context as the ORM service: active companies (allowed_company_ids), lang, tz.
                    // Without it the server falls back to all of the user's companies.
                    context: { ...user.context },
                },
            }).then(backendAction => {
                if (backendAction && backendAction.res_model) {
                    executeAction(backendAction);
                } else {
                    fallbackLocal();
                }
            }).catch(err => {
                console.warn("[HDS Dashboard] get_card_action RPC error, using local fallback:", err);
                fallbackLocal();
            });
            return false;
        }

        fallbackLocal();
        return false;
    };

    // Single record view (e.g. employee click)
    window.hdsRecordClick = function (el, recordId, model) {
        if (!recordId || !model) return;
        const executeRecordAction = () => {
            const actionService = getActionService();
            if (actionService && actionService.doAction) {
                actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: model,
                    res_id: parseInt(recordId, 10),
                    views: [[false, "form"]],
                    target: "current",
                }, { clearBreadcrumbs: false });
            } else {
                console.warn("[HDS Dashboard] ActionService not available yet for record click, retrying...");
                setTimeout(() => {
                    const retryService = getActionService();
                    if (retryService && retryService.doAction) {
                        retryService.doAction({
                            type: "ir.actions.act_window",
                            res_model: model,
                            res_id: parseInt(recordId, 10),
                            views: [[false, "form"]],
                            target: "current",
                        }, { clearBreadcrumbs: false });
                    }
                }, 100);
            }
        };
        executeRecordAction();
    };

    // Delegated click listener to catch card and record clicks exclusively inside dashboard containers
    document.addEventListener("click", function (ev) {
        const dashboardRoot = ev.target.closest(".o_hds_dashboard_root, [data-hds-dashboard-root], .hds-dashboard-container");
        if (!dashboardRoot) {
            return;
        }

        const recBtn = ev.target.closest("[data-record-id]");
        if (recBtn) {
            const rid = recBtn.getAttribute("data-record-id");
            const rmod = recBtn.getAttribute("data-record-model");
            if (rid && rmod) {
                ev.preventDefault();
                ev.stopPropagation();
                window.hdsRecordClick(recBtn, rid, rmod);
                return;
            }
        }

        const card = ev.target.closest(".o_hds_dashboard_card_clickable, [data-card-type]");
        if (card) {
            const ctype = card.getAttribute("data-card-type");
            if (ctype && ctype !== "hr_employee_record") {
                ev.preventDefault();
                ev.stopPropagation();
                window.hdsCardClick(card, ctype);
            }
        }
    }, true);

    // Dynamic Period Update without Full Window / Browser Reload
    window.hdsUpdatePeriod = function (monthNum, fyId) {
        const rootEl = document.querySelector(".o_hds_dashboard_root, [data-hds-dashboard-root]");
        if (rootEl) {
            rootEl.style.transition = "opacity 0.15s ease";
            rootEl.style.opacity = "0.45";
            rootEl.style.pointerEvents = "none";
        }

        const rpcService = window.__hds_rpc || rpc;
        if (!rpcService) {
            console.warn("[HDS Dashboard] RPC service unavailable for dynamic period update.");
            return;
        }

        console.log("[HDS Dashboard] Dynamic period update requested: Month =", monthNum, "FY =", fyId);

        rpcService("/web/dataset/call_kw/hds.payroll.dashboard/set_dashboard_period_and_get_html", {
            model: "hds.payroll.dashboard",
            method: "set_dashboard_period_and_get_html",
            args: [],
            kwargs: {
                month_num: monthNum,
                fy_id: fyId,
                // Same context as the page load (active companies), so the figures do not change on refresh
                context: { ...user.context },
            },
        }).then(result => {
            if (result && result.html) {
                const currentRoot = document.querySelector(".o_hds_dashboard_root, [data-hds-dashboard-root]");
                if (currentRoot) {
                    const tempDiv = document.createElement("div");
                    tempDiv.innerHTML = result.html;
                    const newRoot = tempDiv.firstElementChild || tempDiv;
                    newRoot.style.opacity = "0";
                    newRoot.style.transition = "opacity 0.2s ease";
                    currentRoot.replaceWith(newRoot);
                    requestAnimationFrame(() => {
                        newRoot.style.opacity = "1";
                    });
                }

                // Sync top form fields if present in Form View
                if (result.payroll_month_num) {
                    const formMonthSelect = document.querySelector("[name='payroll_month_num'] select, select[name='payroll_month_num']");
                    if (formMonthSelect) formMonthSelect.value = result.payroll_month_num;
                    const monthToggler = document.querySelector("[name='payroll_month_num'] .o_select_menu_toggler_slot");
                    const monthMap = {
                        "1": "January", "2": "February", "3": "March", "4": "April",
                        "5": "May", "6": "June", "7": "July", "8": "August",
                        "9": "September", "10": "October", "11": "November", "12": "December"
                    };
                    if (monthToggler && monthMap[result.payroll_month_num]) {
                        monthToggler.textContent = monthMap[result.payroll_month_num];
                    }
                }

                if (result.financial_year_name) {
                    const fyToggler = document.querySelector("[name='financial_year_id'] .o_select_menu_toggler_slot, [name='financial_year_id'] input");
                    if (fyToggler) {
                        if (fyToggler.value !== undefined) fyToggler.value = result.financial_year_name;
                        else fyToggler.textContent = result.financial_year_name;
                    }
                }

                // Sync Workforce badge
                if (result.active_employee_count !== undefined) {
                    const empBadge = document.querySelector("[name='active_employee_count']");
                    if (empBadge) empBadge.textContent = result.active_employee_count;
                }

                // Let the control-panel period search follow the saved period
                // (changes can also come from the header's month navigator)
                window.dispatchEvent(new CustomEvent("hds-period-changed", {
                    detail: {
                        month: result.payroll_month_num,
                        fyId: result.financial_year_id,
                    },
                }));

                console.log("[HDS Dashboard] Dynamic period update completed successfully!");
            }
        }).catch(err => {
            console.error("[HDS Dashboard] set_dashboard_period_and_get_html error:", err);
            if (rootEl) {
                rootEl.style.opacity = "1";
                rootEl.style.pointerEvents = "auto";
            }
        });
    };

    // Auto-update when Payroll Month or Tax Year form view dropdown changes
    let periodChangeDebounce = null;
    document.addEventListener("change", function (ev) {
        const target = ev.target;
        if (!target) return;

        // Skip internal dashboard selectors (they use explicit onchange)
        if (target.id === "hds_dashboard_month_picker" || target.id === "hds_dashboard_fy_picker") {
            return;
        }

        const isMonth = target.matches("[name='payroll_month_num'] select, select[name='payroll_month_num']") ||
            target.closest("[name='payroll_month_num']");
        const isYear = target.matches("[name='financial_year_id'] select, select[name='financial_year_id']") ||
            target.closest("[name='financial_year_id']");

        if (isMonth || isYear) {
            clearTimeout(periodChangeDebounce);
            periodChangeDebounce = setTimeout(() => {
                const monthSelect = document.querySelector("[name='payroll_month_num'] select, select[name='payroll_month_num'], [name='payroll_month_num'] input");
                const monthVal = monthSelect ? (monthSelect.value || (monthSelect.dataset && monthSelect.dataset.value)) : null;

                const yearSelect = document.querySelector("[name='financial_year_id'] select, select[name='financial_year_id'], [name='financial_year_id'] input");
                const yearVal = yearSelect ? (yearSelect.value || (yearSelect.dataset && yearSelect.dataset.value)) : null;

                window.hdsUpdatePeriod(monthVal, yearVal);
            }, 80);
        }
    }, true);

    // Support Odoo 19 OWL SelectMenu item selection clicks in FormView
    document.addEventListener("click", function (ev) {
        const choiceItem = ev.target.closest(".o_select_menu_menu .dropdown-item, .o_field_selection_menu .dropdown-item, [data-choice-index]");
        if (choiceItem) {
            setTimeout(() => {
                const monthToggler = document.querySelector("[name='payroll_month_num'] .o_select_menu_toggler_slot, [name='payroll_month_num'] button");
                if (monthToggler) {
                    const text = monthToggler.textContent.trim();
                    const monthMap = {
                        "January": "1", "February": "2", "March": "3", "April": "4",
                        "May": "5", "June": "6", "July": "7", "August": "8",
                        "September": "9", "October": "10", "November": "11", "December": "12"
                    };
                    if (monthMap[text]) {
                        window.hdsUpdatePeriod(monthMap[text], null);
                    }
                }
            }, 60);
        }
    }, true);
    // -------------------------------------------------------------
    // PAY RUN FORM: "More" Dropdown Menu
    // Options:
    // 1. Payroll Journal
    // 2. Re-compute Payslip (same as compute sheet)
    // 3. Add Employee
    // 4. Delete
    // 5. Journal Entry (Draft)
    // -------------------------------------------------------------
    function getActivePayRunInfo() {
        const payrunForm = document.querySelector(".o_payroll_payrun_form") || document.querySelector(".o_form_view");
        if (!payrunForm) return null;

        let resId = null;
        let isDraft = false;

        try {
            const comp = payrunForm.closest(".o_form_view")?.__owl__?.component || payrunForm.__owl__?.component;
            if (comp?.props?.record) {
                if (comp.props.record.resModel === "hr.payslip.run") {
                    resId = comp.props.record.resId;
                    isDraft = comp.props.record.data?.state === "draft";
                }
            }
        } catch (e) { }

        if (!resId) {
            const m = window.location.pathname.match(/\/odoo\/action-\d+\/(\d+)/);
            if (m && document.querySelector(".o_payroll_payrun_form")) {
                resId = parseInt(m[1], 10);
                const isDraftElem = document.querySelector(".o_payroll_payrun_form .badge-warning, .o_payroll_payrun_form button[name='action_batch_validate']");
                isDraft = Boolean(isDraftElem);
            }
        }

        return resId ? { resId, isDraft } : null;
    }

    function injectPayRunMoreMenu() {
        const payrunForm = document.querySelector(".o_payroll_payrun_form");
        if (!payrunForm) return;

        const statusBarButtons = payrunForm.querySelector(".o_statusbar_buttons");
        if (!statusBarButtons) return;

        const info = getActivePayRunInfo();
        if (!info || !info.resId) return;

        const existingDropdown = statusBarButtons.querySelector(".o_payrun_more_dropdown");
        if (existingDropdown) {
            if (existingDropdown.dataset.resId !== String(info.resId)) {
                existingDropdown.dataset.resId = String(info.resId);
            }
            return;
        }

        const container = document.createElement("div");
        container.className = "dropdown d-inline-block o_payrun_more_dropdown ms-1 position-relative";
        container.dataset.resId = String(info.resId);
        container.innerHTML = `
            <button class="btn btn-sm d-flex align-items-center gap-1 o_payrun_more_btn"
                    type="button"
                    aria-expanded="false"
                    style="font-weight: 500; font-size: 13px; height: 32px; padding: 4px 12px; border-radius: 6px; box-shadow: none; cursor: pointer;">
                <span class="fw-semibold">More</span>
                <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" style="margin-left: 2px;">
                    <path d="M7.247 11.14 2.451 5.658C1.885 5.013 2.345 4 3.204 4h9.592a1 1 0 0 1 .753 1.659l-4.796 5.48a1 1 0 0 1-1.506 0z"/>
                </svg>
            </button>
            <ul class="dropdown-menu shadow py-1 o_payrun_more_menu" style="min-width: 190px; border-radius: 8px; z-index: 1050; position: absolute; top: calc(100% + 4px); left: 0;">
                <li>
                    <a class="dropdown-item py-2 px-3 o_payrun_menu_item" href="#" data-menu="payroll_journal" style="font-size: 13.5px; font-weight: 450; cursor: pointer;">
                        Payroll Journal
                    </a>
                </li>
                <li>
                    <a class="dropdown-item py-2 px-3 o_payrun_menu_item" href="#" data-menu="recompute_payslip" style="font-size: 13.5px; font-weight: 450; cursor: pointer;">
                        Re-compute Payslip
                    </a>
                </li>
                <li>
                    <a class="dropdown-item py-2 px-3 o_payrun_menu_item" href="#" data-menu="add_employee" style="font-size: 13.5px; font-weight: 450; cursor: pointer;">
                        Add Employee
                    </a>
                </li>
                <li>
                    <a class="dropdown-item py-2 px-3 o_payrun_menu_item o_payrun_menu_item_danger" href="#" data-menu="delete" style="font-size: 13.5px; font-weight: 450; cursor: pointer;">
                        Delete
                    </a>
                </li>
                <li><hr class="dropdown-divider my-1" style="opacity: 0.1;"></li>
                <li>
                    <a class="dropdown-item py-2 px-3 o_payrun_menu_item d-flex align-items-center gap-2" href="#" data-menu="journal_entry_draft" style="font-size: 13.5px; cursor: pointer;">
                        <span class="o_payrun_menu_icon" style="font-size: 16px; font-weight: bold; line-height: 1;">$</span>
                        <div class="d-flex flex-column" style="line-height: 1.2;">
                            <span style="font-weight: 500;">Journal Entry</span>
                            <span class="text-muted" style="font-size: 11.5px;">(Draft)</span>
                        </div>
                    </a>
                </li>
            </ul>
        `;

        const validateBtn = statusBarButtons.querySelector("button[name='action_batch_validate']");
        if (validateBtn && validateBtn.nextSibling) {
            statusBarButtons.insertBefore(container, validateBtn.nextSibling);
        } else if (validateBtn) {
            statusBarButtons.appendChild(container);
        } else {
            statusBarButtons.appendChild(container);
        }

        const toggleBtn = container.querySelector(".o_payrun_more_btn");
        const menuElem = container.querySelector(".dropdown-menu");

        toggleBtn.addEventListener("click", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            const isVisible = menuElem.style.display === "block";
            document.querySelectorAll(".o_payrun_more_dropdown .dropdown-menu").forEach((m) => {
                m.style.display = "none";
                m.classList.remove("show");
            });
            document.querySelectorAll(".o_payrun_more_dropdown .o_payrun_more_btn").forEach((b) => {
                b.setAttribute("aria-expanded", "false");
            });
            if (!isVisible) {
                menuElem.style.display = "block";
                menuElem.classList.add("show");
                toggleBtn.setAttribute("aria-expanded", "true");
            }
        });
    }

    setInterval(injectPayRunMoreMenu, 250);

    document.addEventListener("click", function (ev) {
        if (!ev.target.closest(".o_payrun_more_dropdown")) {
            document.querySelectorAll(".o_payrun_more_dropdown .dropdown-menu").forEach((m) => {
                m.style.display = "none";
                m.classList.remove("show");
            });
            document.querySelectorAll(".o_payrun_more_dropdown .o_payrun_more_btn").forEach((b) => {
                b.setAttribute("aria-expanded", "false");
            });
        }
    });

    document.addEventListener("click", async function (ev) {
        const item = ev.target.closest(".o_payrun_menu_item");
        if (!item) return;

        ev.preventDefault();
        ev.stopPropagation();

        const dropdownMenu = item.closest(".dropdown-menu");
        if (dropdownMenu) {
            dropdownMenu.style.display = "none";
            dropdownMenu.classList.remove("show");
            const toggle = dropdownMenu.parentElement.querySelector(".o_payrun_more_btn");
            if (toggle) {
                toggle.setAttribute("aria-expanded", "false");
            }
        }

        const info = getActivePayRunInfo();
        if (!info || !info.resId) {
            console.warn("[PayRunMoreMenu] No active Pay Run resId found.");
            return;
        }

        const resId = info.resId;
        const menuKey = item.dataset.menu;
        const actService = getActionService();

        async function callModelMethod(model, method, args = [], kwargs = {}) {
            const orm = window.__hds_orm || globalOrmService || document.querySelector(".o_form_view")?.__owl__?.component?.env?.services?.orm || window.odoo?.__WOWL_DEBUG__?.root?.env?.services?.orm;
            if (orm && typeof orm.call === "function") {
                return await orm.call(model, method, args, kwargs);
            }
            return await rpc(`/web/dataset/call_kw/${model}/${method}`, {
                model,
                method,
                args,
                kwargs: { ...kwargs, context: { ...user.context, ...(kwargs.context || {}) } },
            });
        }

        try {
            if (menuKey === "payroll_journal") {
                const action = await callModelMethod("hr.payslip.run", "action_view_payroll_journal", [[resId]]);
                if (action && actService) {
                    await actService.doAction(action);
                }
            } else if (menuKey === "recompute_payslip") {
                const action = await callModelMethod("hr.payslip.run", "action_recompute_payslips", [[resId]]);
                const notifService = window.__hds_notification || globalNotificationService;
                if (notifService && action?.params?.message) {
                    notifService.add(action.params.message, {
                        type: "success",
                        title: action.params.title,
                    });
                }
                if (actService) {
                    await actService.doAction({ type: "ir.actions.client", tag: "reload" });
                }
            } else if (menuKey === "add_employee") {
                if (actService) {
                    await actService.doAction("hudson_payroll_base.action_hr_payslip_by_employees", {
                        additionalContext: {
                            active_id: resId,
                            active_ids: [resId],
                            active_model: "hr.payslip.run",
                            default_payslip_run_id: resId,
                        },
                        onClose: async () => {
                            if (actService) {
                                await actService.doAction({ type: "ir.actions.client", tag: "reload" });
                            }
                        },
                    });
                }
            } else if (menuKey === "delete") {
                const onConfirmDelete = async () => {
                    const action = await callModelMethod("hr.payslip.run", "action_delete_payrun", [[resId]]);
                    if (action && actService) {
                        await actService.doAction(action);
                    } else if (actService) {
                        await actService.doAction({
                            type: "ir.actions.act_window",
                            name: "Pay Runs",
                            res_model: "hr.payslip.run",
                            view_mode: "kanban,list,form",
                            views: [[false, "kanban"], [false, "list"], [false, "form"]],
                            target: "current",
                        });
                    }
                };

                const dialogService = window.__hds_dialog || globalDialogService ||
                    document.querySelector(".o_form_view")?.__owl__?.component?.env?.services?.dialog ||
                    document.querySelector(".o_web_client")?.__owl__?.component?.env?.services?.dialog;

                const bodyMsg = deleteConfirmationMessage ||
                    "Ready to make your record disappear into thin air? Are you sure?\nIt will be gone forever!\n\nThink twice before you click that 'Delete' button!";
                const titleMsg = "Bye-bye, record!";
                const confirmLabel = "Delete";
                const cancelLabel = "No, keep it";

                let dialogOpened = false;
                if (dialogService && typeof dialogService.add === "function" && ConfirmationDialog) {
                    try {
                        dialogService.add(ConfirmationDialog, {
                            title: titleMsg,
                            body: bodyMsg,
                            confirmLabel: confirmLabel,
                            confirmClass: "btn-danger",
                            cancelLabel: cancelLabel,
                            confirm: onConfirmDelete,
                            cancel: () => { },
                        });
                        dialogOpened = true;
                    } catch (err) {
                        console.warn("[PayRunMoreMenu] Native ConfirmationDialog failed, using modal fallback:", err);
                    }
                }

                if (!dialogOpened) {
                    const existingModal = document.getElementById("o_payrun_delete_confirm_modal");
                    if (existingModal) existingModal.remove();

                    const modalBackdrop = document.createElement("div");
                    modalBackdrop.id = "o_payrun_delete_confirm_modal";
                    modalBackdrop.className = "modal fade show d-block";
                    modalBackdrop.tabIndex = -1;
                    modalBackdrop.style.backgroundColor = "rgba(0, 0, 0, 0.4)";
                    modalBackdrop.style.zIndex = "1055";

                    modalBackdrop.innerHTML = `
                        <div class="modal-dialog modal-dialog-centered" style="max-width: 440px;">
                            <div class="modal-content shadow border-0 o_payrun_confirm_content" style="border-radius: 12px; overflow: hidden;">
                                <div class="modal-header border-0 pb-1 pt-3 px-4 d-flex justify-content-between align-items-center">
                                    <h5 class="modal-title fw-bold mb-0 o_payrun_confirm_title" style="font-size: 18px;">${titleMsg}</h5>
                                    <button type="button" class="btn-close" aria-label="Close" style="font-size: 12px; cursor: pointer;"></button>
                                </div>
                                <div class="modal-body px-4 py-2 o_payrun_confirm_body" style="font-size: 14px; line-height: 1.5; white-space: pre-wrap;">${bodyMsg}</div>
                                <div class="modal-footer border-0 pt-2 pb-3 px-4 d-flex justify-content-start gap-2">
                                    <button type="button" class="btn btn-danger px-3 py-1 fw-semibold o_confirm_delete_btn" style="border-radius: 6px; font-size: 13.5px; background-color: #ef4444; border-color: #ef4444; color: #ffffff; cursor: pointer;">
                                        ${confirmLabel}
                                    </button>
                                    <button type="button" class="btn btn-outline-secondary px-3 py-1 fw-semibold o_cancel_delete_btn" style="border-radius: 6px; font-size: 13.5px; cursor: pointer;">
                                        ${cancelLabel}
                                    </button>
                                </div>
                            </div>
                        </div>
                    `;

                    document.body.appendChild(modalBackdrop);

                    const closeModal = () => modalBackdrop.remove();
                    modalBackdrop.querySelector(".btn-close").addEventListener("click", closeModal);
                    modalBackdrop.querySelector(".o_cancel_delete_btn").addEventListener("click", closeModal);
                    modalBackdrop.addEventListener("click", (e) => {
                        if (e.target === modalBackdrop) closeModal();
                    });

                    modalBackdrop.querySelector(".o_confirm_delete_btn").addEventListener("click", async () => {
                        closeModal();
                        await onConfirmDelete();
                    });
                }
            } else if (menuKey === "journal_entry_draft") {
                const action = await callModelMethod("hr.payslip.run", "action_open_draft_journal_entry", [[resId]]);
                if (action && actService) {
                    await actService.doAction(action);
                }
            }
        } catch (err) {
            console.error("[PayRunMoreMenu] Action failed:", menuKey, err);
        }
    }, true);
})();

