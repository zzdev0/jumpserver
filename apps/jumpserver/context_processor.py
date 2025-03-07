# -*- coding: utf-8 -*-
#
from django.templatetags.static import static
from django.conf import settings
from django.utils.translation import ugettext as _


def jumpserver_processor(request):
    # Setting default pk
    context = {
        'DEFAULT_PK': '00000000-0000-0000-0000-000000000000',
        'LOGO_URL': static('img/logo.png'),
        'LOGO_TEXT_URL': static('img/logo_text.png'),
        'LOGIN_IMAGE_URL': static('img/login_image.jpg'),
        'FAVICON_URL': static('img/facio.ico'),
        'LOGIN_CAS_LOGO_URL': static('img/login_cas_logo.png'),
        'LOGIN_WECOM_LOGO_URL': static('img/login_wecom_logo.png'),
        'LOGIN_DINGTALK_LOGO_URL': static('img/login_dingtalk_logo.png'),
        'LOGIN_FEISHU_LOGO_URL': static('img/login_feishu_logo.png'),
        'JMS_TITLE': _('JumpServer Open Source Bastion Host'),
        'VERSION': settings.VERSION,
        'COPYRIGHT': 'FIT2CLOUD 飞致云' + ' © 2014-2021',
        'SECURITY_COMMAND_EXECUTION': settings.SECURITY_COMMAND_EXECUTION,
        'SECURITY_MFA_VERIFY_TTL': settings.SECURITY_MFA_VERIFY_TTL,
        'FORCE_SCRIPT_NAME': settings.FORCE_SCRIPT_NAME,
        'SECURITY_VIEW_AUTH_NEED_MFA': settings.SECURITY_VIEW_AUTH_NEED_MFA,
        'LOGIN_CONFIRM_ENABLE': settings.LOGIN_CONFIRM_ENABLE,
    }
    return context



