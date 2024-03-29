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

class ResPartner(models.Model):
    _inherit="res.partner"

    is_mobile_app_user = fields.Boolean(string="Is a Mobile App User", copy=False)
    mobile_app_status = fields.Selection(selection=[('online','Online'),('offline','Offline')], default="offline")

    def toggle_is_mobile_app(self):
        for user in self:
            if self.is_mobile_app_user:
                self.is_mobile_app_user = False
            else:
                self.is_mobile_app_user = True

    def name_get(self):
        if self.env.context.get('name_get_override', False):
            res = []
            for record in self:
                res.append((record.id, record.name+" [ Online ]" if record.mobile_app_status == 'online' else record.name+" [ Offline ]"))
            return res

        return super(ResPartner,self).name_get()
