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

from odoo import models, fields, api, SUPERUSER_ID, _
import random, json, re
from .fcmAPI import FCMAPI
from odoo.http import request
from odoo.osv import expression
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


def _get_image_url(base_url, model_name, record_id, field_name, write_date=0, width=0, height=0):
    """
    Returns a local url that points to the image field of a given browse record.
    """
    if base_url and not base_url.endswith("/"):
        base_url = base_url + "/"
    if width or height:
        return '%sweb/image/%s/%s/%s/%sx%s?unique=%s' % (
            base_url, model_name, record_id, field_name, width, height, re.sub('[^\d]', '', write_date))
    else:
        return '%sweb/image/%s/%s/%s?unique=%s' % (
            base_url, model_name, record_id, field_name, re.sub('[^\d]', '', write_date))


class MobileAppConfig(models.Model):
    _name = 'mobile.app.config'
    _description = 'mobile app config'

    def _default_language(self):
        lc = self.env['ir.default'].get('res.partner', 'lang')
        dl = self.env['res.lang'].search([('code', '=', lc)], limit=1)
        return dl.id if dl else self.env['res.lang'].search([]).ids[0]

    def _active_languages(self):
        return self.env['res.lang'].search([]).ids

    # def _default_currency(self):
    #     super_usr_id = self.env['res.users'].sudo().browse(SUPERUSER_ID)
    #     return super_usr_id and super_usr_id.company_id and super_usr_id.company_id.currency_id and super_usr_id.company_id.currency_id.id or False

    name = fields.Char('Title', default="Mobile App Configuration", required=1)
    api_key = fields.Char(string='API Secret key', default="ac0a13e739-465a-ac366c0-f7-31bdde5c1", required=1)
    default_lang = fields.Many2one('res.lang', string='Default Language', default=_default_language,
                                   help="If the selected language is loaded in the Delivery Boy, all documents related to "
                                        "this contact will be printed in this language. If not, it will be English.")

    language_ids = fields.Many2many('res.lang', 'mobile_app_lang_rel', 'mobile_app_id', 'lang_id', 'Languages',
                                    default=_active_languages)
    db_reset_password = fields.Boolean(string='Enable pwd reset',
                                       help="This allows users to trigger a password reset from App")
    show_banner = fields.Boolean(help="Allow this to show the Mobile App banner in App")
    verify_token = fields.Boolean(help="Before order confirmation token will be verified")
    db_banner = fields.Binary('Banner')
    # currency_id = fields.Many2one('res.currency', string='Default Currency', default=_default_currency)

    fcm_api_key = fields.Char(string='FCM Api key')

    def check_mobile_app_addons(self):
        result = {}
        ir_model_obj = self.env['ir.module.module'].sudo()
        # result['mobikul'] = ir_model_obj.search([('state', '=', 'installed'),('name', '=', 'mobikul')]) and True or False
        return result

    def _get_currency(self):
        response = {}
        try:
            self.ensure_one()
            response = {
                'code': self.db_program_id.currency_id.name,
                'symbol': self.db_program_id.currency_id.symbol,
                'position': self.db_program_id.currency_id.position
            }
        except Exception:
            pass

        return response

    @api.model
    def _validate(self, api_key, context=None):
        # super_usr_id = self.env['res.users'].sudo().browse(SUPERUSER_ID).company_id.currency_id
        context = context or {}
        response = {'success': False, 'responseCode': 400, 'message': _('Unknown Error !!!')}
        if not api_key:
            response['responseCode'] = 401
            response['message'] = _('Invalid/Missing Api Key !!!')
            return response
        try:
            # Get Mobile App Configuration
            mobile_app_config = self.env['mobile.app.config'].sudo().search([], limit=1)
            if not mobile_app_config:
                response['responseCode'] = 501
                response['message'] = _("Mobile App Configuration not found !!!")
            elif mobile_app_config.api_key != api_key:
                response['responseCode'] = 401
                response['message'] = _("API Key is invalid !!!")
            else:
                response['success'] = True
                response['responseCode'] = 200
                response['message'] = _('Login successfully.')
                response['lang'] = context.get(
                    'lang') or mobile_app_config.default_lang and mobile_app_config.default_lang.code or "en_US"
                response['currency'] = mobile_app_config._get_currency()
                # local data should be removed when sending the final response from controller
                company_id = self.env['res.company'].sudo().search([], limit=1)
                response['local'] = {
                    'lang_obj': self.env['res.lang']._lang_get(response['lang']),
                    'tz': 'Asia/Bahrain',
                    'allowed_company_ids': [company_id.id],
                    'default_company_id': company_id.id,
                    'lang': response['lang'],
                }
                response['addons'] = self.check_mobile_app_addons()
        except Exception as e:
            response['responseCode'] = 400
            response['message'] = _("Login Failed:") + "%r" % e
        return response

    @api.model
    def _get_image_url(self, model_name, record_id, field_name, write_date=0, width=0, height=0, context=None):
        """ Returns a local url that points to the image field of a given browse record. """
        context = context or {}
        if context.get('base_url', "") and not context['base_url'].endswith("/"):
            context['base_url'] = context['base_url'] + "/"
        if width or height:
            return '%sweb/image/%s/%s/%s/%sx%s?unique=%s' % (
                context.get('base_url'), model_name, record_id, field_name, width, height,
                re.sub('[^\d]', '', write_date))
        else:
            return '%sweb/image/%s/%s/%s?unique=%s' % (
                context.get('base_url'), model_name, record_id, field_name, re.sub('[^\d]', '', write_date))

    @api.model
    def fetch_user_info(self, user_obj, context=None):
        context = context or {}
        temp_i = {
            'clientProfileImage': self._get_image_url('res.partner', user_obj.partner_id.id, 'image_1920',
                                                      user_obj.partner_id.write_date.__str__(), context=context),
            'clientName': user_obj.partner_id.name or "",
            'clientEmail': user_obj.login or "",
            'clientPhone': user_obj.phone or "",
        }
        return temp_i

    @api.model
    def getDefaultData(self, website_id):
        try:
            self.ensure_one()
        except ValueError:
            self = self.sudo().search([], limit=1)
        temp = {}
        temp['allowResetPwd'] = self.db_reset_password
        temp['category_ids'] = self.get_website_categories(website_id)
        temp['state_ids'] = self.get_states(website_id)
        temp['city_ids'] = self.get_cities(website_id)
        temp['shipping_methode_ids'] = self.get_shipping_methodes(website_id)
        temp['payment_methode_ids'] = self.get_payment_methodes(website_id)
        temp['occasion_ids'] = self.get_occasion_ids()
        temp['showBanner'] = self.show_banner
        temp['verifyToken'] = self.verify_token
        if self.show_banner:
            temp['bannerImage'] = self._get_image_url('mobile.app.config', self.id, 'db_banner',
                                                      self.write_date.__str__(),
                                                      context={'base_url': self._context.get('base_url')})
        return temp

    @api.model
    def authenticate(self, credentials, detailed=False, isSocialLogin=False, context=None):
        context = context or {}
        response = {'success': False, 'responseCode': 400, 'message': _('Unknown Error !!!')}
        user = False
        if not isinstance(credentials, dict):
            response['message'] = _('Data is not in Dictionary format !!!')
            return response
        if isSocialLogin:
            if not all(k in credentials for k in ('authProvider', 'authUserId')):
                response['message'] = _('Insufficient data to authenticate !!!')
                return response
            provider = self._getAuthProvider(credentials['authProvider'])
            try:
                user = self.env['res.users'].sudo().search(
                    [('oauth_uid', '=', credentials['authUserId']), ('oauth_provider_id', '=', provider),
                     ('partner_id.is_delivery_boy', '=', True)])
                if not user:
                    response['responseCode'] = 404
                    response['message'] = _("Social-Login: No such record found.")
            except Exception as e:
                response['message'] = _("Social-Login Failed")
                response['details'] = "%r" % e
        else:
            if not all(k in credentials for k in ('login', 'pwd')):
                response['message'] = _('Insufficient data to authenticate !!!')
                return response
            try:
                user = self.env['res.users'].sudo().search(
                    [('login', '=', credentials['login']), ('partner_id.is_mobile_app_user', '=', True)])
                if user:

                    user.with_user(user.id)._check_credentials(credentials['pwd'], {'interactive': True})
                else:
                    response['responseCode'] = 400
                    response['message'] = _("Invalid password/email address.")
            except Exception as e:
                user = False
                response['responseCode'] = 400
                response['message'] = _("Login Failed")
                response['details'] = "%r" % e
        if user:
            try:
                response['success'] = True
                response['responseCode'] = 200
                response['clientPartnerId'] = user.partner_id.id
                response['status'] = user.partner_id.delivery_boy_status
                response['userId'] = user.id
                response['message'] = _('Login successfully.')
                if detailed:
                    response.update(self.fetch_user_info(user, context=context))
            except Exception as e:
                response['responseCode'] = 400
                response['message'] = _("Login Failed")
                response['details'] = "%r" % e
        return response

    def _getAddress(self, db_picking):
        partner = db_picking.picking_id.partner_id

        customer_address = "%s,%s,%s,%s,%s,%s" % (
            partner.street or '',
            partner.street2 or '',
            partner.city or '',
            partner.state_id and partner.state_id.name or '',
            partner.zip or '',
            partner.country_id and partner.country_id.name or '',
        )
        return customer_address

    def _formattedValue(self, value, symbol, position='after'):
        if position != 'after':
            return "%s%d" % (symbol, value)
        return "%d%s" % (value, symbol)

    @api.model
    def getProducts(self, website_id=False, category_id=False, **kwargs):
        domain = ['&', '&', ('is_published', '=', True), ('public_categ_ids', 'child_of', int(category_id)),
                  ('website_ids', 'in', (False, website_id))]
        result = []
        products = self.env['product.template'].sudo().search(domain)
        for product in products:
            result.append(self._getProductDetails(product, website_id))
        return result

    def get_website_categories(self, website_id=False, category_id=False, **kwargs):
        domain = ['|', ('website_id', '=', website_id), ('website_id', '=', False)]
        result = []
        category_obj = self.env['product.public.category'].sudo()
        categories = category_obj.search(domain)
        for category in categories:
            result.append(self._getCategoryDetails(category))
        return result

    def get_shipping_methodes(self, website_id=False, **kwargs):
        domain = ['|', ('website_id', '=', website_id), ('website_id', '=', False)]
        result = []
        delivery_carrier_obj = self.env['delivery.carrier'].sudo()
        delivery_carriers = delivery_carrier_obj.search(domain)
        for delivery_carrier in delivery_carriers:
            result.append(self._getDeliveryCarrierDetails(delivery_carrier))
        return result

    def get_occasion_ids(self, **kwargs):
        result = []
        occassion_obj = self.env['product.occasion'].sudo()
        occassions = occassion_obj.search([])
        for occassion in occassions:
            result.append(self._getOccassionDetails(occassion))
        return result

    def get_payment_methodes(self, website_id=False, **kwargs):
        domain = ['|', '&', ('website_id', '=', website_id), ('website_id', '=', False), ('state', '=', 'enabled')]
        result = []
        payment_provider_obj = self.env['payment.provider'].sudo()
        payment_providers = payment_provider_obj.search(domain)
        for provider in payment_providers:
            result.append(self._getPaymentProvideDetails(provider))
        return result

    def get_time_stots(self, website_id=False, **kwargs):
        website = self.env['website'].sudo().browse(website_id)
        result = []
        if website:
            domain = [('company_id', '=', website.company_id.id)]
            time_stot_obj = self.env['time.slot'].sudo()
            time_stots = time_stot_obj.search(domain)

            for slot in time_stots:
                result.append(self._getTimeSlotDetails(slot))
        return result

    def get_states(self, website_id=False, **kwargs):
        website = self.env['website'].sudo().browse(website_id)
        result = []
        if website:
            domain = [('country_id', '=', website.company_id.country_id.id)]
            state_obj = self.env['res.country.state'].sudo()
            states = state_obj.search(domain)

            for state in states:
                result.append(self._getStateDetails(state))
        return result

    def get_cities(self, website_id=False, **kwargs):
        website = self.env['website'].sudo().browse(website_id)
        result = []
        if website:
            domain = [('country_id', '=', website.company_id.country_id.id)]
            result = []
            city_obj = self.env['res.city'].sudo()
            cities = city_obj.search(domain)
            for city in cities:
                result.append(self._getCityDetails(city))
        return result

    def _getCityDetails(self, city):
        details = {
            'id': city.id or -1,
            'name': city.name or '',
            'state_id': city.state_id.id or -1,
        }
        return details

    def _getStateDetails(self, slot):
        details = {
            'id': slot.id or -1,
            'name': slot.name or '',
        }
        return details

    def _getTimeSlotDetails(self, state):
        details = {
            'id': state.id or -1,
            'name': state.name or '',
        }
        return details

    def _getPaymentProvideDetails(self, provider):
        details = {
            'id': provider.id or -1,
            'name': provider.name or '',
            'adyen_api_key': provider.adyen_api_key or '',
            'adyen_client_key': provider.adyen_client_key or '',
            'adyen_hmac_key': provider.adyen_hmac_key or '',
            'adyen_checkout_api_url': provider.adyen_checkout_api_url or '',
            'adyen_recurring_api_url': provider.adyen_recurring_api_url or '',
        }
        return details

    def _getDeliveryCarrierDetails(self, delivery_carrier):
        details = {
            'id': delivery_carrier.id or -1,
            'name': delivery_carrier.name or '',
            'fixed_price': delivery_carrier.fixed_price or 0,
            'product_id': delivery_carrier.product_id.id or -1,
            'amount': delivery_carrier.amount or 0,
        }
        return details
    def _getOccassionDetails(self, occassion):
        details = {
            'id': occassion.id or -1,
            'name': occassion.name or '',
        }
        return details
    def _getCategoryDetails(self, category):
        details = {
            'id': category.id or '',
            'name': category.name or '',
            'description': category.description or '',
            'parent_id': category.parent_id.id or -1,
            'image': self._get_image_url('product.public.category', category.id, 'image_1920',
                                         category.write_date.__str__(),
                                         context={'base_url': self.env['ir.config_parameter'].sudo().get_param(
                                             'web.base.url', default='')}),
        }
        return details

    def _getProductDetails(self, product, website_id):
        pricelist = self.env['product.pricelist'].search([('website_id', '=', website_id), ('active', '=', True)],
                                                         limit=1)
        if not pricelist:
            pricelist = self.env['website'].browse(website_id).get_current_website().get_current_pricelist()

        extra_images = []
        extra_images.append(
            self._get_image_url('product.template', product.id, 'image_1920', product.write_date.__str__(),
                                context={'base_url': self.env['ir.config_parameter'].sudo().get_param(
                                    'web.base.url', default='')}))
        for image in product.product_template_image_ids:
            extra_images.append(
                self._get_image_url('product.image', image.id, 'image_1920', product.write_date.__str__(),
                                    context={'base_url': self.env['ir.config_parameter'].sudo().get_param(
                                        'web.base.url', default='')}))

        attribute_line_ids = []
        for line in product.attribute_line_ids:
            value_ids = []
            for value in line.value_ids:
                value_ids.append({
                    'id': value.id,
                    'value': value.name,
                    # Add more fields as needed
                })
            item = {
                'attribute_id': line.attribute_id.id,
                'attribute_name': line.attribute_id.name,
                'value_ids': value_ids,
            }
            attribute_line_ids.append(item)

        product_variant_ids = []
        for variant in product.product_variant_ids:
            attribute_value_ids = []

            for record in variant.product_template_attribute_value_ids:
                attribute_value_ids.append({
                    'attribute_id': record.attribute_id.id,
                    'attribute_name': record.attribute_id.name,
                    'value_ids': [{
                        'id': record.product_attribute_value_id.id,
                        'value': record.product_attribute_value_id.name,
                    }]
                    # Add more fields as needed
                })
            item = {
                'product_tmpl_id': variant.product_tmpl_id.id,
                'id': variant.id,
                'name': variant.display_name,
                'variant_price': int(variant._get_combination_info_variant(add_qty=1, pricelist=pricelist,
                                                                           parent_combination=False)['price']),
                'attribute_value_ids': attribute_value_ids,
            }
            product_variant_ids.append(item)
        occasion_ids = []
        for occasion in product.occasion_ids:
            occasion_ids.append({
                'id': occasion.id,
                'name': occasion.name,
            })
        color_ids = []
        for color in product.color_ids:
            color_ids.append({
                'id': color.id,
                'name': color.name,
            })
        spec_ids = []
        for spec in product.spec_ids:
            spec_ids.append({
                'id': spec.id,
                'name': spec.name,
            })
        details = {
            'id': product.id or '',
            'name': product.name or '',
            'sequence': product.website_sequence or '',
            'title': html2plaintext(product.subtitile) or '',
            'description': html2plaintext(product.description_sale) or '',
            'customer_care': html2plaintext(product.customer_care) or '',
            'price': int(product._get_price_by_website(website_id, pricelist.id)) or '',
            'image': self._get_image_url('product.template', product.id, 'image_1920', product.write_date.__str__(),
                                         context={'base_url': self.env['ir.config_parameter'].sudo().get_param(
                                             'web.base.url', default='')}),
            'images': extra_images,
            'image_detail': html2plaintext(product.image_detail) or '',
            'occasion_ids': occasion_ids,
            'spec_ids': spec_ids,
            'color_ids': color_ids,
            'accessory_product_ids': product.accessory_product_ids.ids or '',
            'alternative_product_ids': product.alternative_product_ids.ids or '',
            'attribute_line_ids': attribute_line_ids,
            'product_variant_ids': product_variant_ids,

        }
        return details

    @api.model
    def resetPassword(self, login):
        response = {'success': False, 'responseCode': 400}
        try:
            res_users = self.env['res.users'].sudo()
            if login:
                user = res_users.search([('login', '=', login)])
                if user:
                    if user.partner_id.is_delivery_boy:
                        res_users.reset_password(login)
                        response['responseCode'] = 200
                        response['success'] = True
                        response['message'] = _("An email has been sent with credentials to reset your password")
                    else:
                        response['message'] = _('User is not registered as a delivery boy.')
                else:
                    raise Exception
            else:
                response['message'] = _("No login provided.")
        except Exception as e:
            response['message'] = _("Invalid Username/Email.")
        return response


class MobileAppPushNotificationTemplate(models.Model):
    _name = 'mobile.app.push.notification.template'
    _description = 'Mobile App Push Notification Templates'
    _order = "name"

    def _addMe(self, data):
        _id = self.env["mobile.app.notification.messages"].sudo().create(data)
        return True

    def _get_key(self):
        mobile_app_config = self.env['mobile.app.config'].sudo().search([], limit=1)
        return mobile_app_config and mobile_app_config.fcm_api_key or ""

    @api.model
    def _pushMe(self, key, payload_data, data=False):
        status = True
        summary = ""
        # _logger.info("---------------payload_data------------%r---", payload_data)
        try:
            push_service = FCMAPI(api_key=key)
            summary = push_service.send([payload_data])
            if data:
                self._addMe(data)
        except Exception as e:
            status = False
            summary = "Error: %r" % e
        return [status, summary]

    def _customize_notification_title(self, db_picking):
        return re.sub("_", db_picking and db_picking.name or "", self.notification_title)

    def _customize_notification_body(self, db_picking):
        return re.sub("_", db_picking and db_picking.name or "", self.notification_body)

    @api.model
    def _send(self, to_data, partner_id=False, db_picking=False, max_limit=20):
        """
        to_data = dict(to or registration_ids)
        """
        if type(to_data) != dict:
            return False
        if not to_data.get("to", False) and not to_data.get("registration_ids", False):
            if not partner_id:
                return False
            reg_data = self.env['mobile.app.fcm.registered.devices'].sudo().search_read(
                [('partner_id', '=', partner_id)], limit=max_limit, fields=['token'])
            if not reg_data:
                return False
            to_data = {
                "registration_ids": [r['token'] for r in reg_data]
            }
        # notification = dict(title=self.notification_title, body=self.notification_body)
        notification = dict(id=random.randint(1, 99999), title=self._customize_notification_title(db_picking),
                            body=self._customize_notification_body(db_picking), sound="default")
        if self.notification_color:
            notification['color'] = self.notification_color
        if self.notification_tag:
            notification['tag'] = self.notification_tag

        fcm_payload = dict(notification=notification)
        fcm_payload.update(to_data)
        data_message = dict(type="", id="", domain="", image="", name="")

        if self.banner_action == 'picking':
            data_message['type'] = 'picking'
        elif self.banner_action == 'invoice':
            data_message['type'] = 'invoice'
        else:
            data_message['type'] = 'none'
        data_message['image'] = _get_image_url(self._context.get('base_url') or request.httprequest.base_url,
                                               'mobile.app.push.notification.template', self.id, 'image_128',
                                               self.write_date.__str__())
        data_message['notificationId'] = random.randint(1, 99999)
        fcm_payload['data'] = data_message
        if partner_id:
            data = dict(
                title=self._customize_notification_title(db_picking),
                body=self._customize_notification_body(db_picking),
                partner_id=partner_id,
                banner=self.image, datatype='default'
            )
        return self._pushMe(self._get_key(), json.dumps(fcm_payload).encode('utf8'), partner_id and data or False)

    name = fields.Char('Name', required=True, translate=True)
    notification_color = fields.Char('Color', default='PURPLE')
    notification_tag = fields.Char('Tag')
    notification_title = fields.Char('Title', required=True, translate=True)
    active = fields.Boolean(default=True, copy=False)
    notification_body = fields.Text('Body', translate=True)
    image = fields.Binary('Image', attachment=True)
    banner_action = fields.Selection([
        ('picking', 'Open Pickings Page'),
        ('invoice', 'Open Invoices Page'),
        ('none', 'Do nothing')],
        string='Action', required=True,
        default='none',
        help="Define what action will be triggerred when click/touch on the banner.")
    device_id = fields.Many2one('mobile.app.fcm.registered.devices', string='Select Device')
    total_views = fields.Integer('Total # Views', default=0, readonly=1, copy=False)
    condition = fields.Selection([
        ('p_assigned', "Picking Assigned"),
        ('p_canceled', "Picking Canceled"),
        ('p_invoiced', "Picking Commission Invoiced"),
        ('p_paid', "Picking Commission Paid")
    ], string='Condition')

    def dry_run(self):
        self.ensure_one()
        to_data = dict(to=self.device_id and self.device_id.token or "")
        result = self._send(to_data,
                            self.device_id and self.device_id.partner_id and self.device_id.partner_id.id or False)
        # raise UserError('Result: %r'%result)

    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {}, name=_('%s(copy)') % self.name)
        return super(MobileAppPushNotificationTemplate, self).copy(default)


class MobileAppPushNotification(models.Model):
    _name = 'mobile.app.push.notification'
    _description = 'Mobile App Push Notification'
    _order = "activation_date, name"
    _inherit = ['mobile.app.push.notification.template']

    @api.model
    def parse_n_push(self, max_limit=20, registration_ids=None):
        to_data = dict()
        if self.notification_type == 'token-auto':
            reg_data = self.env['mobile.app.fcm.registered.devices'].sudo().search_read(limit=max_limit,
                                                                                        fields=['token'])
            registration_ids = [r['token'] for r in reg_data]
        elif self.notification_type == 'token-manual':
            registration_ids = [d.token for d in self.device_ids]
        # elif self.notification_type == 'topic':
        #     to_data['to'] = '/topics/%s' % self.topic_id.name
        else:
            return [False, "Insufficient Data"]

        if registration_ids:
            if len(registration_ids) > 1:
                to_data['registration_ids'] = registration_ids
            else:
                to_data['to'] = registration_ids[0]
        return self._send(to_data)

    summary = fields.Text('Summary', readonly=True)
    activation_date = fields.Datetime('Activation Date', copy=False)
    notification_type = fields.Selection([
        ('token-auto', 'Token-Based(All Reg. Devices)'),
        ('token-manual', 'Token-Based(Selected Devices)'),
        # ('topic', 'Topic-Based'),
    ],
        string='Type', required=True,
        default='token-auto')
    # topic_id = fields.Many2one('fcm.registered.topics', string='Choose Topic')
    device_ids = fields.Many2many('mobile.app.fcm.registered.devices',
                                  'mobile_app_fcm_registered_devices_push_notif_rel', string='Choose Devices/Customers')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirm'),
        ('hold', 'Hold'),
        ('error', 'Error'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, default='draft')

    def action_cancel(self):
        for record in self:
            record.state = 'cancel'
        return True

    def action_confirm(self):
        for record in self:
            record.state = 'confirm'
        return True

    def action_draft(self):
        for record in self:
            record.state = 'draft'
        return True

    def action_hold(self):
        for record in self:
            record.state = 'hold'
        return True

    def push_now(self):
        for record in self:
            response = record.parse_n_push()
            record.state = response and response[0] and 'done' or 'error'
            record.summary = response and response[1] or ''
        return True

    def duplicate_me(self):
        self.ensure_one()
        action = self.env.ref('mobile_app.mobile_app_push_notification_action').read()[0]
        action['views'] = [(self.env.ref('mobile_app.mobile_app_push_notification_view_form').id, 'form')]
        action['res_id'] = self.copy().id
        return action


class MobileAppNotificationMessages(models.Model):
    _name = 'mobile.app.notification.messages'
    _description = 'Mobile App Notification Messages'

    name = fields.Char('Message Name', default='/', index=True, copy=False, readonly=True)
    title = fields.Char('Title')
    subtitle = fields.Char('Subtitle')
    body = fields.Text('Body')
    # icon = fields.Binary('Icon')
    banner = fields.Binary('Banner')
    is_read = fields.Boolean('Is Read', default=False, readonly=True)
    partner_id = fields.Many2one('res.partner', string="Delivery Boy", index=True,
                                 domain=[('is_delivery_boy', '=', True)])
    active = fields.Boolean(default=True, readonly=True)
    # period = fields.Char('Period',compute='_compute_period')
    datatype = fields.Selection([
        ('default', 'Default'),
        ('order', 'Order')],
        string='Data Type', required=True,
        default='default',
        help="Notification Messages Data Type for your Delivery Boy App.")

    @api.model
    def create(self, vals):
        vals['name'] = self.env['ir.sequence'].next_by_code('mobile.app.notification.messages')
        return super(MobileAppNotificationMessages, self).create(vals)

    # def _compute_period(self):
    #     for i in self:
    #         i.period = self.env['mobile.app.config'].easy_date(i.create_date)


class MobileAppFcmRegisteredDevices(models.Model):
    _name = 'mobile.app.fcm.registered.devices'
    _description = 'All Registered Devices on FCM for Push Notifications.'
    _order = 'write_date desc'

    def name_get(self):
        res = []
        for record in self:
            name = record.partner_id and record.partner_id.name or ''
            res.append((record.id, "%s(DeviceId:%s)" % (name, record.device_id)))
        return res

    name = fields.Char('Name')
    token = fields.Text('FCM Registration ID', readonly=True)
    device_id = fields.Char('Device Id', readonly=True)
    partner_id = fields.Many2one('res.partner', string="Client", readonly=True, index=True)
    active = fields.Boolean(default=True, readonly=True)
    # write_date = fields.Datetime(string='Last Update', readonly=True, help="Date on which this entry is created.")
    description = fields.Text('Description', readonly=True)
