# -*- coding: utf-8 -*-
from odoo import models
from odoo.orm.domains import Domain

class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def _get_applicable_rules_domain(self, products, **kwargs):
        domain = super()._get_applicable_rules_domain(products, **kwargs)
        extra_domains = []
        
        plan_id = self.env.context.get('subscription_plan_id')
        if plan_id:
            extra_domains.append(Domain('subscription_plan_id', '=', plan_id))
        else:
            extra_domains.append(Domain('subscription_plan_id', '=', False))
            
        packaging_id = self.env.context.get('product_packaging_id')
        if packaging_id:
            extra_domains.append(Domain('packaging_id', 'in', (packaging_id, False)))
        else:
            extra_domains.append(Domain('packaging_id', '=', False))
            
        return Domain.AND([domain, *extra_domains])


