# -*- coding: utf-8 -*-

from odoo import models, fields, api
from requests.utils import requote_uri


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_price_by_website(self,website_id,pricelis_id):
        if website_id and self.product_variant_count > 1:
            pricelist = self.env['product.pricelist'].browse(pricelis_id)
            prices = []
            for variant in self.product_variant_ids:
                combination_info = variant._get_combination_info_variant(add_qty=1, pricelist=pricelist,
                                                                         parent_combination=False)
                prices.append(combination_info['price'])
            return min(prices)
        else:
            return self.list_price



class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    description = fields.Char('Description')