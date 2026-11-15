# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ProjectProject(models.Model):
    """Extend project.project to hold a reference to the originating Sale Order.

    This field is the bridge that enables the SO → Project → Field Service
    billing flow. When a SO with a service product is confirmed, Odoo may
    auto-create a project; our hook in SaleOrder.action_confirm() will then
    stamp sale_order_id on that project.

    If the sale_timesheet / sale_project modules are installed, they may
    already define sale_order_id — Odoo's field-merge mechanism handles that
    gracefully; we do NOT redefine a field that already exists.
    """
    _inherit = 'project.project'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Originating Sale Order',
        copy=False,
        help=(
            'The sale order that originated this project. '
            'Materials added to linked field service orders will be '
            'invoiced against this sale order.'
        ),
    )


class ProjectTask(models.Model):
    """Expose the project's sale_order_id as a direct field on tasks."""
    _inherit = 'project.task'

    project_sale_order_id = fields.Many2one(
        'sale.order',
        related='project_id.sale_order_id',
        string='Project Sale Order',
        store=False,
        readonly=True,
        help='The sale order linked to this task\'s project.',
    )


class SaleOrder(models.Model):
    """Hook into SO confirmation to auto-link the created project to the SO.

    Works with sale_project / sale_timesheet modules by checking for the
    existence of sale.order.line fields dynamically.  If those modules are
    not installed the hook does nothing — no error is raised.
    """
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            order._link_projects_to_sale_order()
        return res

    def _link_projects_to_sale_order(self):
        """
        After SO confirmation, find any project(s) that were auto-created
        from service-product lines and stamp their sale_order_id.

        Supports two mechanisms used by different Odoo modules:
          1. sale_project  →  sale.order.line has ``project_id``
          2. sale_timesheet →  sale.order.line has ``task_id`` with project_id
        """
        self.ensure_one()
        for line in self.order_line:
            if line.product_id.type != 'service':
                continue

            # Mechanism 1: line.project_id (sale_project / sale_timesheet)
            line_project = getattr(line, 'project_id', False)
            if line_project and not line_project.sale_order_id:
                line_project.sale_order_id = self
                continue

            # Mechanism 2: line.task_id.project_id (sale_timesheet)
            line_task = getattr(line, 'task_id', False)
            if line_task and line_task.project_id and not line_task.project_id.sale_order_id:
                line_task.project_id.sale_order_id = self
