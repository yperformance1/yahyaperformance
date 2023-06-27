# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################
import logging
_logger = logging.getLogger(__name__)
from odoo import models,fields,api, _

class ResUsers(models.Model):
    _inherit="res.users"

    is_mobile_app_user = fields.Boolean(string="Is a Mobile App User", copy=False, related='partner_id.is_mobile_app_user')

    def toggle_is_mobile_app(self):
        for user in self:
            if self.is_mobile_app_user:
                self.partner_id.is_mobile_app = False
            else:
                self.partner_id.is_mobile_app = True
