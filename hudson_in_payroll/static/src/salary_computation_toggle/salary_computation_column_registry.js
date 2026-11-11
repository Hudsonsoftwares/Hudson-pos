/** @odoo-module **/

import { Registry } from "@web/core/registry";

export const salaryComputationColumnsRegistry = new Registry();

// Mandatory Columns (Cannot be hidden)
salaryComputationColumnsRegistry.add("name", {
    name: "name",
    label: "Salary Rule Name",
    mandatory: true,
    defaultVisible: true,
    sequence: 10,
});

salaryComputationColumnsRegistry.add("total", {
    name: "total",
    label: "Total",
    mandatory: true,
    defaultVisible: true,
    sequence: 100,
});

// Optional Columns (Can be toggled visible / hidden)
salaryComputationColumnsRegistry.add("code", {
    name: "code",
    label: "Salary Rule Code",
    mandatory: false,
    defaultVisible: true,
    sequence: 20,
});

salaryComputationColumnsRegistry.add("category_id", {
    name: "category_id",
    label: "Category",
    mandatory: false,
    defaultVisible: true,
    sequence: 30,
});

salaryComputationColumnsRegistry.add("sequence", {
    name: "sequence",
    label: "Sequence",
    mandatory: false,
    defaultVisible: false,
    sequence: 40,
});

salaryComputationColumnsRegistry.add("quantity", {
    name: "quantity",
    label: "Quantity",
    mandatory: false,
    defaultVisible: true,
    sequence: 50,
});

salaryComputationColumnsRegistry.add("rate", {
    name: "rate",
    label: "Rate (%)",
    mandatory: false,
    defaultVisible: true,
    sequence: 60,
});

salaryComputationColumnsRegistry.add("amount", {
    name: "amount",
    label: "Base",
    mandatory: false,
    defaultVisible: true,
    sequence: 70,
});

salaryComputationColumnsRegistry.add("salary_rule_id", {
    name: "salary_rule_id",
    label: "Rule Description",
    mandatory: false,
    defaultVisible: true,
    sequence: 80,
});

salaryComputationColumnsRegistry.add("account_debit", {
    name: "account_debit",
    label: "Debit Account",
    mandatory: false,
    defaultVisible: false,
    sequence: 85,
});

salaryComputationColumnsRegistry.add("account_credit", {
    name: "account_credit",
    label: "Credit Account",
    mandatory: false,
    defaultVisible: false,
    sequence: 90,
});
