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
{
    "name": "Ecommerce Mobile App",
    "summary": """This module allows you to assign delivery boys and manage delivery of orders through native mobile application.""",
    "version": "1.0.2",
    "sequence": 1,
    "author": "Webkul Software Pvt. Ltd.",
    "license": "Other proprietary",
    "maintainer": "Anuj Kumar Chhetri",
    "website": "",
    "description": """Ecommerce Mobile App""",
    "live_test_url": "http://demo.webkul.com/web/login",
    "depends": [
        'website_sale',
    ],
    "data": [
        'security/ir.model.access.csv',
        'views/mobile_app_config_view.xml',
        'views/res_config_settings_view.xml',
        'views/product_template.xml',

    ],
    "demo": ['demo/demo.xml'],
    "images": ['static/description/odoo-delivery-boy-v15.gif'],
    "application": True,
    "installable": True,
    "auto_install": False,
    "price": 299,
    "currency": "USD",
}
