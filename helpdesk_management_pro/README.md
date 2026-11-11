# Helpdesk Management Pro

## Overview
Helpdesk Management Pro is a comprehensive application for handling customer support tickets efficiently. It provides advanced SLA policies, assignment rules, time tracking, portal views, and integrations with after-sales processes like refunds, gift cards, and field service orders.

## Configuration & Installation
1. Install the module via Odoo Apps interface.
2. Ensure dependencies like `mail`, `portal`, `project` and `sale_management` are installed.
3. Configure Helpdesk Teams under Helpdesk > Configuration > Teams.
4. Define SLAs and assign them to specific Teams or Priority levels.

## Features
- Dynamic SLA Deadlines and Warnings
- Automatic Ticket Assignment Methods (Random, Balanced, Tags)
- Integrated Action Buttons (Refund, Replace, Return, Plan Field Service)
- Livechat and WhatsApp Webhook Hooks

## Known Limitations
- The auto-close cron operates strictly per-team, so performance may slightly vary on instances with thousands of distinct teams.
- WhatsApp data ingestion relies on an external mapping API payload currently defined in `create_ticket_from_whatsapp`.

## Version History
- **1.1.4**: Code remediation fixes for dashboard performance, security, and assignment robustness.
- **1.1**: Added Field Service, Refund wizard integration, and SLA multi-tier policies.
- **1.0**: Initial Release

## Pre-requisites & Dependencies
This module runs completely standalone on standard Odoo Community Edition (Odoo 20).
All dependencies (`base`, `mail`, `portal`, `website`, `project`, `crm`, `account`, `stock`, `loyalty`, `repair`, etc.) are official standard Odoo modules.
No third-party or custom external modules are required.
