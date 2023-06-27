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

from odoo.http import request, Controller, route
from odoo import tools, _
import json, werkzeug
from base64 import b64decode
from functools import wraps
from ast import literal_eval
from datetime import datetime
from odoo.tools import email_normalize
from odoo.exceptions import AccessError, MissingError, ValidationError


class xml(object):

    @staticmethod
    def _encode_content(data):
        # .replace('&', '&amp;')
        return data.replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    @classmethod
    def dumps(cls, apiName, obj):
        _logger.warning("%r : %r" % (apiName, obj))
        if isinstance(obj, dict):
            return "".join("<%s>%s</%s>" % (key, cls.dumps(apiName, obj[key]), key) for key in obj)
        elif isinstance(obj, list):
            return "".join(
                "<%s>%s</%s>" % ("I%s" % index, cls.dumps(apiName, element), "I%s" % index) for index, element in
                enumerate(obj))
        else:
            return "%s" % (xml._encode_content(obj.__str__()))

    @staticmethod
    def loads(string):
        def _node_to_dict(node):
            if node.text:
                return node.text
            else:
                return {child.tag: _node_to_dict(child) for child in node}

        root = ET.fromstring(string)
        return {root.tag: _node_to_dict(root)}


class MobileAppServices(Controller):

    def _wrap2xml(self, apiName, data):
        resp_xml = "<?xml version='1.0' encoding='UTF-8'?>"
        resp_xml += '<odoo xmlns:xlink="http://www.w3.org/1999/xlink">'
        resp_xml += "<%s>" % apiName
        resp_xml += xml.dumps(apiName, data)
        resp_xml += "</%s>" % apiName
        resp_xml += '</odoo>'
        return resp_xml

    def _response(self, apiName, response, ctype='json'):
        if 'local' in response:
            response.pop("local")
        if ctype == 'json':
            mime = 'application/json; charset=utf-8'
            body = json.dumps(response)
        else:
            mime = 'text/xml'
            body = self._wrap2xml(apiName, response)
        headers = [
            ('Content-Type', mime),
            ('Content-Length', len(body))
        ]
        return werkzeug.wrappers.Response(body, headers=headers)

    def _checkProvidedData(self, neededData=set()):
        response = {}
        if neededData - {key for key in self._mData}:
            response['responseCode'] = 400
            response['success'] = False
            response['message'] = _('Insufficient Data Provided !!!')
        return response

    def __decorateMe(func):
        @wraps(func)
        def wrapped(inst, *args, **kwargs):
            inst._mData = request.httprequest.data and json.loads(request.httprequest.data.decode('utf-8')) or {}
            inst._mAuth = request.httprequest.authorization and (
                    request.httprequest.authorization.get('password') or request.httprequest.authorization.get(
                "username")) or None
            inst.base_url = request.httprequest.host_url
            inst._lcred = {}
            inst._sLogin = False
            inst.auth = True
            inst._mLang = request.httprequest.headers.get("lang") or None
            if request.httprequest.headers.get("Login"):
                try:
                    inst._lcred = literal_eval(b64decode(request.httprequest.headers["Login"]).decode('utf-8'))
                except:
                    inst._lcred = {"login": None, "pwd": None}
            elif request.httprequest.headers.get("SocialLogin"):
                inst._sLogin = True
                try:
                    inst._lcred = literal_eval(b64decode(request.httprequest.headers["SocialLogin"]).decode('utf-8'))
                except:
                    inst._lcred = {"authProvider": 1, "authUserId": 1234567890}
            else:
                inst.auth = False
            return func(inst, *args, **kwargs)

        return wrapped

    def _check_date(self, date):
        if not date:
            return False
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')
        return date_obj >= datetime.strptime(today, '%Y-%m-%d')

    def values_preprocess(self, values):
        new_values = dict()
        partner_fields = request.env['res.partner']._fields

        for k, v in values.items():
            # Convert the values for many2one fields to integer since they are used as IDs
            if k in partner_fields and partner_fields[k].type == 'many2one':
                new_values[k] = bool(v) and int(v)
            # Store empty fields as `False` instead of empty strings `''` for consistency with other applications like
            # Contacts.
            elif v == '':
                new_values[k] = False
            else:
                new_values[k] = v

        return new_values

    def checkout_form_validate(self, mode, all_form_values, data):
        # mode: tuple ('new|edit', 'billing|shipping')
        # all_form_values: all values before preprocess
        # data: values after preprocess
        error = dict()
        error_message = []

        # prevent name change if invoices exist
        if data.get('partner_id'):
            partner = request.env['res.partner'].browse(int(data['partner_id']))
            if partner.exists() and partner.name and not partner.sudo().can_edit_vat() and 'name' in data and (
                    data['name'] or False) != (partner.name or False):
                error['name'] = 'error'
                error_message.append(
                    _('Changing your name is not allowed once invoices have been issued for your account. Please contact us directly for this operation.'))

        # Required fields from form
        required_fields = [f for f in (all_form_values.get('field_required') or '').split(',') if f]

        # Required fields from mandatory field function
        country_id = int(data.get('country_id', False))
        required_fields += mode[1] == 'shipping' and self._get_mandatory_fields_shipping(
            country_id) or self._get_mandatory_fields_billing(country_id)

        # error message for empty required fields
        for field_name in required_fields:
            if not data.get(field_name):
                error[field_name] = 'missing'

        # email validation
        if data.get('email') and not tools.single_email_re.match(data.get('email')):
            error["email"] = 'error'
            error_message.append(_('Invalid Email! Please enter a valid email address.'))

        # vat validation
        Partner = request.env['res.partner']
        if data.get("vat") and hasattr(Partner, "check_vat"):
            if country_id:
                data["vat"] = Partner.fix_eu_vat_number(country_id, data.get("vat"))
            partner_dummy = Partner.new(self._get_vat_validation_fields(data))
            try:
                partner_dummy.check_vat()
            except ValidationError as exception:
                error["vat"] = 'error'
                error_message.append(exception.args[0])

        if [err for err in error.values() if err == 'missing']:
            error_message.append(_('Some required fields are empty.'))

        return error, error_message
    def _checkout_form_save(self, checkout):
        Partner = request.env['res.partner']
        partner_id = Partner.sudo().with_context(tracking_disable=True).create(checkout).id

        return partner_id
    def values_postprocess(self, mode, values, errors, error_msg, website_id):
        new_values = {}
        authorized_fields = request.env['ir.model']._get('res.partner')._get_form_writable_fields()
        for k, v in values.items():
            # don't drop empty value, it could be a field to reset
            if k in authorized_fields and v is not None:
                new_values[k] = v
            else:  # DEBUG ONLY
                if k not in ('field_required', 'partner_id', 'callback', 'submitted'):  # classic case
                    _logger.debug("website_sale postprocess: %s value has been dropped (empty or not writable)" % k)

        new_values['website_id'] = website_id
        website = request.env['website'].sudo().browse(website_id)

        if mode[0] == 'new':
            new_values['company_id'] = website.company_id.id

        return new_values, errors, error_msg

    @__decorateMe
    def _authenticate(self, auth, **kwargs):
        if 'api_key' in kwargs:
            api_key = kwargs.get('api_key')
        elif request.httprequest.authorization:
            api_key = request.httprequest.authorization.get('password') or request.httprequest.authorization.get(
                "username")
        else:
            api_key = False

        mobile_app_config = request.env['mobile.app.config'].sudo()
        response = mobile_app_config._validate(api_key, {"lang": self._mLang})
        if not response.get('success'):
            return response
        context = response['local']
        context['base_url'] = self.base_url
        request.update_context = dict(request.context, **context)
        # if auth:
        #	result = mobile_app_config.with_context(context).authenticate(self._lcred, kwargs.get('detailed',False),self._sLogin, context={'base_url':self.base_url})
        #	response.update(result)
        return response

    @route(['/mobileApp/confirm_order/<int:website_id>'], csrf=False, type='http', auth="public", methods=['POST'])
    def confirm_order(self, website_id=False, **kw):
        response = self._authenticate(True, **kw)
        if response.get('success'):
            response['success'] = False
            response['responseCode'] = 400
            mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
            try:
                is_pickup = False
                partner_invoice_id = False
                partner_shipping_id = False
                mode = (False, False)
                order_carrier_id = False
                order_commitment_date = False
                order_time_slot = False
                order_delivery_note = False
                order_gift_message = False
                order_gift_message_from = False
                order_hide_sender_name = False
                order_call_receiver = False
                order_delivery_pickup = False
                values, errors, post_billing, post_shipping = {}, {}, {}, {}
                error_message = []
                website = request.env['website'].sudo().browse(website_id)


                if request.httprequest.method in ["POST"]:
                    # select existing address

                    if kw.get('bill-id') and kw.get('bill-id') != "-1":
                        partner_invoice_id = int(kw.get('bill-id'))
                    else:
                        mode = ('new', False)
                        kw_billing = {
                            "firstname": kw.get('firstname_billing'),
                            "lastname": kw.get('lastname_billing'),
                            "email": kw.get('email_billing'),
                            "phone_code": kw.get('phone_code_billing'),
                            "phone": kw.get('phone_billing'),
                        }
                        pre_values = self.values_preprocess(kw_billing)
                        # errors_billing, error_msg = self.checkout_form_validate(mode, kw_billing, pre_values)
                        errors_billing = dict()
                        error_msg = []
                        post_billing, errors_billing, error_msg = self.values_postprocess(mode, pre_values,
                                                                                          errors_billing,
                                                                                          error_msg, website_id)

                        if errors_billing:
                            if 'firstname' in errors_billing: errors["firstname_billing"] = errors_billing.get(
                                'firstname')
                            if 'lastname' in errors_billing: errors["lastname_billing"] = errors_billing.get('lastname')
                            if 'email' in errors_billing: errors["email_billing"] = errors_billing.get('email')
                            if 'phone' in errors_billing: errors["phone_billing"] = errors_billing.get('phone')
                            error_message = list(set(error_message + error_msg))
                        else:
                            post_billing['name'] = kw_billing.get('firstname') + ' ' + kw_billing.get('lastname')
                            post_billing['phone_code'] = '+' + str(kw_billing.get('phone_code'))
                            post_billing['type'] = "contact"

                    if kw.get('delivery_type'):
                        is_pickup = kw.get('delivery_type') == '1'
                        carrier_id = request.env['delivery.carrier'].sudo().browse(int(kw.get('delivery_type')))
                        if carrier_id:
                            order_carrier_id = carrier_id.id

                    delivery_date = kw.get('delivery_date', False)
                    time_slot = kw.get('time_slot', False)
                    if time_slot and self._check_date(delivery_date):
                        order_commitment_date = datetime.strptime(delivery_date, '%Y-%m-%d')
                        order_time_slot = int(time_slot)
                    else:
                        errors["time_slot"] = 'error'
                        errors["delivery_date"] = 'error'
                        error_message.append(_('Please select a valid date and time slot.'))

                    if is_pickup:
                        if kw.get('pick_up_location'):
                            partner_pick_up_location = request.env['res.partner'].sudo().browse(
                                int(kw.get('pick_up_location')))
                            partner_shipping_id = partner_pick_up_location.id
                        else:
                            errors["pick_up_location"] = 'error'
                            error_message.append(_('Please choose a pickup location.'))
                    else:

                        # select existing address
                        if kw.get('ship-id') and kw.get('ship-id') != "-1":
                            partner_shipping_id = int(kw.get('ship-id'))

                        else:
                            mode = ('new', 'shipping')
                            pre_values = self.values_preprocess(kw)
                            # errors_shipping, error_msg = self.checkout_form_validate(mode, kw, pre_values)
                            errors_shipping = dict()
                            error_msg = []
                            post_shipping, errors_shipping, error_msg = self.values_postprocess(mode, pre_values,
                                                                                                errors_shipping,
                                                                                                error_msg, website_id)
                            post_shipping['country_id'] = website.company_id.country_id.id

                            if errors_shipping:
                                errors.update(errors_shipping)
                                error_message = list(set(error_message + error_msg))

                            else:
                                post_shipping['name'] = kw.get('firstname') + ' ' + kw.get('lastname')
                                post_shipping['street2'] = post_shipping['street2'] or '' + ', ' + kw.get(
                                    'street3') or ''
                                post_shipping['phone_code'] = '+' + str(kw.get('phone_code'))
                                post_shipping['zip'] = post_shipping['zip'] if 'zip' in post_shipping else False

                    order_delivery_note = kw.get('delivrey_instruction')
                    order_gift_message = kw.get('card_message').replace('\n', '<br>')
                    order_gift_message_from = kw.get('card_message_from')
                    hide_sender = kw.get('hide_sender', 'off')
                    call_receiver = kw.get('call_receiver', 'off')

                    order_hide_sender_name = True if hide_sender == 'on' else False
                    order_call_receiver = True if call_receiver == 'on' else False

                    if is_pickup:
                        order_delivery_pickup = 'pickup'
                    else:
                        order_delivery_pickup = 'delivery'

                    if errors:
                        errors['error_message'] = error_message
                        response['errors'] = errors
                        response['success'] = False
                        return self._response('confirm_order', response)

                    else:
                        pricelist = request.env['product.pricelist'].sudo().search(
                            [('website_id', '=', website.id)],
                            limit=1)
                        order = request.env['sale.order'].sudo().create({
                            'partner_id': website.partner_id.id,
                            'company_id': website.company_id.id,
                            'pricelist_id': pricelist.id if pricelist else website.get_current_pricelist().id,
                            'carrier_id': order_carrier_id,
                            'commitment_date': order_commitment_date,
                            'time_slot': order_time_slot,
                            'delivery_note': order_delivery_note,
                            'gift_message': order_gift_message,
                            'gift_message_from': order_gift_message_from,
                            'hide_sender_name': order_hide_sender_name,
                            'call_receiver': order_call_receiver,
                            'delivery_pickup': order_delivery_pickup,
                        })

                        if partner_invoice_id:
                            order.partner_invoice_id = partner_invoice_id
                        else:
                            post_shipping['company_id'] = False
                            existing_partner_id = request.env['res.partner'].sudo().search(
                                [('email', '=', post_billing['email']), ('type', '=', 'contact')], limit=1)
                            if existing_partner_id:
                                existing_partner_id.company_id = False
                                partner_invoice_id = existing_partner_id.id
                            else:
                                partner_invoice_id = self._checkout_form_save( post_billing)
                            order.partner_id = partner_invoice_id
                            order.partner_invoice_id = partner_invoice_id
                            post_shipping['parent_id'] = partner_invoice_id

                        if partner_shipping_id:
                            order.partner_shipping_id = partner_shipping_id
                        else:
                            post_shipping['company_id'] = False
                            partner_shipping_id = self._checkout_form_save(post_shipping)
                            order.partner_shipping_id = partner_shipping_id

                        group_portal = request.env.ref('base.group_portal')
                        group_public = request.env.ref('base.group_public')

                        User = request.env['res.users']
                        user_sudo = User.sudo().search([('login', '=', order.partner_id.email)])

                        if not user_sudo:
                            # create a user if necessary and make sure it is in the portal group
                            user_sudo = User.sudo().with_context(no_reset_password=True)._create_user_from_template({
                                'email': email_normalize(order.partner_id.email),
                                'login': email_normalize(order.partner_id.email),
                                'password': 'password',
                                'partner_id': order.partner_id.id,
                                'company_id': request.env.company.id,
                                'company_ids': [(6, 0, request.env.company.ids)],
                            })
                            user_sudo.write({'active': True, 'groups_id': [(4, group_portal.id), (3, group_public.id)]})

                        response['order'] = order.name


            except Exception as e:
                response['message'] = _("Order not confirmed:") + "%r" % e


        return self._response('confirm_order', response)

    @route('/mobileApp/splashPageData/<int:website_id>', csrf=False, type='http', auth="public", methods=['GET'])
    def getSplashPageData(self, website_id=False, **kwargs):
        response = self._authenticate(False, **kwargs)
        local = response.get('local')
        if response.get('success'):
            mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
            if self.auth:
                result = mobile_app_config.authenticate(self._lcred, True, self._sLogin,
                                                        context={'base_url': self.base_url})
                response.update(result)
                self._tokenUpdate(partner_id=response.get('clientPartnerId', False))
            result = mobile_app_config.getDefaultData(website_id=website_id)
            response.update(result)
            response.update(self._languageData())
            response.pop('lang', None)
        return self._response('splashPageData', response)

    def _languageData(self):
        mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
        temp = {
            'defaultLanguage': (mobile_app_config.default_lang.code, mobile_app_config.default_lang.name),
            'allLanguages': [(id.code, id.name) for id in mobile_app_config.language_ids]
        }

        return temp

    @route('/mobileApp/login', csrf=False, type='http', auth="none", methods=['POST'])
    def login(self, **kwargs):
        kwargs['detailed'] = True
        response = self._authenticate(True, **kwargs)
        self._tokenUpdate(partner_id=response.get('deliveryBoyPartnerId'))
        return self._response('login', response)

    @route('/mobileApp/resetPassword', csrf=False, type='http', auth="none", methods=['POST'])
    def resetPassword(self, **kwargs):
        response = self._authenticate(False, **kwargs)
        if response.get('success'):
            mobile_app_config = request.env['mobile.app.config'].sudo()
            result = mobile_app_config.resetPassword(self._mData.get('login', False))
            response.update(result)
        return self._response('resetPassword', response)

    @route('/mobileApp/logOut', csrf=False, type='http', auth="none", methods=['POST'])
    def signOut(self, **kwargs):
        response = self._authenticate(False, **kwargs)
        if response.get('success'):
            response['message'] = _("Have a Good Day !!!")
            self._tokenUpdate()
        return self._response('signOut', response)

    def _tokenUpdate(self, partner_id=False):
        FcmRegister = request.env['mobile.app.fcm.registered.devices'].sudo()
        already_registered = FcmRegister.search([('device_id', '=', self._mData.get("fcmDeviceId"))])
        if already_registered:
            already_registered.write(
                {'token': partner_id and self._mData.get("fcmToken") or False, 'partner_id': partner_id})
        else:
            FcmRegister.create({
                'token': self._mData.get("fcmToken", ""),
                'device_id': self._mData.get("fcmDeviceId", ""),
                'description': "%r" % self._mData,
                'partner_id': partner_id,
            })
        return True

    @route(['/mobileApp/products/<int:website_id>/category/<int:category_id>'], csrf=False, type='http', auth="public",
           methods=['GET'])
    def mobileAppProducts(self, website_id=False, category_id=False, **kwargs):
        response = self._authenticate(True, **kwargs)
        if response.get('success'):
            response['success'] = False
            response['responseCode'] = 400
            mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
            try:
                if website_id:
                    website = request.env['website'].sudo().browse(website_id)
                    try:
                        website.ensure_one()
                        response['products'] = mobile_app_config.getProducts(
                            website_id, category_id,
                            limit=kwargs.get('limit') and int(kwargs.get('limit')),
                            offset=kwargs.get('offset') and int(kwargs.get('offset')),
                            order=kwargs.get('order'),
                        )
                        response['responseCode'] = 200
                        response['message'] = _('Successfully retrieved the Products.')
                        response['success'] = True

                    except Exception:
                        response['message'] = _('Error. Invalid id.')

            except Exception as e:
                response['message'] = _('Products not Found')
        # response['message'] = e

        return self._response('pickings', response)

    @route('/mobileApp/ShippingMethode/<int:website_id>', csrf=False, type='http', auth="public", methods=['GET'])
    def getShippingMethode(self, website_id=False, **kwargs):
        response = self._authenticate(False, **kwargs)
        if response.get('success'):
            response['success'] = False
            response['responseCode'] = 400
            mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
            try:
                if website_id:
                    website = request.env['website'].sudo().browse(website_id)
                    try:
                        website.ensure_one()
                        response['ShippingMethodeData'] = mobile_app_config.get_shipping_methodes(
                            website_id,
                            limit=kwargs.get('limit') and int(kwargs.get('limit')),
                            offset=kwargs.get('offset') and int(kwargs.get('offset')),
                            order=kwargs.get('order'),
                        )
                        response['responseCode'] = 200
                        response['message'] = _('Successfully retrieved the Shipping Methode.')
                        response['success'] = True
                    except Exception:
                        response['message'] = _('Error. Invalid id.')
            except Exception as e:
                response['message'] = _('Shipping Methode not Found')
        return self._response('ShippingMethodeData', response)

    @route('/mobileApp/PaymentMethode/<int:website_id>', csrf=False, type='http', auth="public", methods=['GET'])
    def getPaymentMethode(self, website_id=False, **kwargs):
        response = self._authenticate(False, **kwargs)
        if response.get('success'):
            response['success'] = False
            response['responseCode'] = 400
            mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
            try:
                if website_id:
                    website = request.env['website'].sudo().browse(website_id)
                    try:
                        website.ensure_one()
                        response['PaymentMethodeData'] = mobile_app_config.get_payment_methodes(
                            website_id,
                            limit=kwargs.get('limit') and int(kwargs.get('limit')),
                            offset=kwargs.get('offset') and int(kwargs.get('offset')),
                            order=kwargs.get('order'),
                        )
                        response['responseCode'] = 200
                        response['message'] = _('Successfully retrieved the Payment Methode.')
                        response['success'] = True
                    except Exception:
                        response['message'] = _('Error. Invalid id.')
            except Exception as e:
                response['message'] = _('Payment Methode not Found')
        return self._response('PaymentMethodeData', response)

    @route('/mobileApp/TimeSlot/<int:website_id>', csrf=False, type='http', auth="public", methods=['GET'])
    def getTimeSlot(self, website_id=False, **kwargs):
        response = self._authenticate(False, **kwargs)
        if response.get('success'):
            response['success'] = False
            response['responseCode'] = 400
            mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
            try:
                if website_id:
                    website = request.env['website'].sudo().browse(website_id)
                    try:
                        website.ensure_one()
                        response['TimeSlotData'] = mobile_app_config.get_time_stots(
                            website_id,
                            limit=kwargs.get('limit') and int(kwargs.get('limit')),
                            offset=kwargs.get('offset') and int(kwargs.get('offset')),
                            order=kwargs.get('order'),
                        )
                        response['responseCode'] = 200
                        response['message'] = _('Successfully retrieved the Time Slots.')
                        response['success'] = True
                    except Exception:
                        response['message'] = _('Error. Invalid id.')
            except Exception as e:
                response['message'] = _('Time Slot not Found')
        return self._response('TimeSlotData', response)

    @route('/mobileApp/State/<int:website_id>', csrf=False, type='http', auth="public", methods=['GET'])
    def getState(self, website_id=False, **kwargs):
        response = self._authenticate(False, **kwargs)
        if response.get('success'):
            response['success'] = False
            response['responseCode'] = 400
            mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
            try:
                if website_id:
                    website = request.env['website'].sudo().browse(website_id)
                    try:
                        website.ensure_one()
                        response['StatesData'] = mobile_app_config.get_states(
                            website_id,
                            limit=kwargs.get('limit') and int(kwargs.get('limit')),
                            offset=kwargs.get('offset') and int(kwargs.get('offset')),
                            order=kwargs.get('order'),
                        )
                        response['responseCode'] = 200
                        response['message'] = _('Successfully retrieved the States.')
                        response['success'] = True
                    except Exception:
                        response['message'] = _('Error. Invalid id.')
            except Exception as e:
                response['message'] = _('States not Found')
        return self._response('StateData', response)

    @route('/mobileApp/City/<int:website_id>', csrf=False, type='http', auth="public", methods=['GET'])
    def getCity(self, website_id=False, **kwargs):
        response = self._authenticate(False, **kwargs)
        if response.get('success'):
            response['success'] = False
            response['responseCode'] = 400
            mobile_app_config = request.env['mobile.app.config'].sudo().search([], limit=1)
            try:
                if website_id:
                    website = request.env['website'].sudo().browse(website_id)
                    try:
                        website.ensure_one()
                        response['CityData'] = mobile_app_config.get_cities(
                            website_id,
                            limit=kwargs.get('limit') and int(kwargs.get('limit')),
                            offset=kwargs.get('offset') and int(kwargs.get('offset')),
                            order=kwargs.get('order'),
                        )
                        response['responseCode'] = 200
                        response['message'] = _('Successfully retrieved the Cities.')
                        response['success'] = True
                    except Exception:
                        response['message'] = _('Error. Invalid id.')
            except Exception as e:
                response['message'] = _('Cities not Found')
        return self._response('CityData', response)
