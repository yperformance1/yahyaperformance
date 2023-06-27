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

class ResConfigSettings(models.TransientModel):
    _inherit="res.config.settings"

    db_config_id = fields.Many2one(comodel_name='mobile.app.config', config_parameter="mobile_app.db_config_id")
    auto_validate = fields.Boolean(config_parameter="mobile_app.auto_validate")
    auto_invoice = fields.Boolean(config_parameter="mobile_app.auto_invoice")
    verify_token = fields.Boolean(related="db_config_id.verify_token", readonly=False)
    mobile_token_mail_temp_id = fields.Many2one(comodel_name="mail.template", config_parameter="mobile_app.mobile_token_mail_temp_id")


    @api.model
    def get_mobile_app_db_configuration(self):
        params = self.env['ir.config_parameter'].sudo()
        config = {
        'program': self.env['mobile.app.programs'].sudo().browse(int(params.get_param('mobile_app.db_program_id'))) or False,
        'auto_validate': params.get_param('mobile_app.auto_validate') and True or False,
        'auto_invoice': params.get_param('mobile_app.auto_invoice') and True or False,
        'verify_token': self.env['mobile.app.config'].sudo().search([], limit=1).verify_token,
        'mobile_token_mail_temp_id': self.env['mail.template'].sudo().browse(int(params.get_param('mobile_app.mobile_token_mail_temp_id'))) or False,
        }
        return config


    def open_mobile_app_conf(self):
        response = {}
        # mobile_app_config = self.env['mobile.app.config'].sudo().search([], limit=1)
        params = self.env['ir.config_parameter'].sudo()
        db_config_id = params.get_param('mobile_app.db_config_id') or False
        if db_config_id:
            response.update({'res_id': int(db_config_id)})

        response.update({
        'type': 'ir.actions.act_window',
        'name': 'Mobile App Configuration',
        'view_mode': 'form',
        'res_model': 'mobile.app.config',
        'target': 'current'
        })

        return response
