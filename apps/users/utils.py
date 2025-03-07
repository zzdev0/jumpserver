# ~*~ coding: utf-8 ~*~
#
import os
import re
import pyotp
import base64
import logging
import time

from django.conf import settings
from django.utils.translation import ugettext as _
from django.core.cache import cache

from common.tasks import send_mail_async
from common.utils import reverse, get_object_or_none, get_request_ip_or_data, get_request_user_agent
from .models import User


logger = logging.getLogger('jumpserver')


def construct_user_created_email_body(user):
    default_body = _("""
        <div>
            <p>Your account has been created successfully</p>
            <div>
                Username: %(username)s
                <br/>
                Password: <a href="%(rest_password_url)s?token=%(rest_password_token)s">
                click here to set your password</a> 
                (This link is valid for 1 hour. After it expires, <a href="%(forget_password_url)s?email=%(email)s">request new one</a>)
            </div>
            <div>
                <p>---</p>
                <a href="%(login_url)s">Login direct</a>
            </div>
        </div>
        """) % {
        'username': user.username,
        'rest_password_url': reverse('authentication:reset-password', external=True),
        'rest_password_token': user.generate_reset_token(),
        'forget_password_url': reverse('authentication:forgot-password', external=True),
        'email': user.email,
        'login_url': reverse('authentication:login', external=True),
    }

    if settings.EMAIL_CUSTOM_USER_CREATED_BODY:
        custom_body = '<p style="text-indent:2em">' + settings.EMAIL_CUSTOM_USER_CREATED_BODY + '</p>'
    else:
        custom_body = ''
    body = custom_body + default_body
    return body


def send_user_created_mail(user):
    recipient_list = [user.email]
    subject = _('Create account successfully')
    if settings.EMAIL_CUSTOM_USER_CREATED_SUBJECT:
        subject = settings.EMAIL_CUSTOM_USER_CREATED_SUBJECT

    honorific = '<p>' + _('Hello %(name)s') % {'name': user.name} + ':</p>'
    if settings.EMAIL_CUSTOM_USER_CREATED_HONORIFIC:
        honorific = '<p>' + settings.EMAIL_CUSTOM_USER_CREATED_HONORIFIC + ':</p>'

    body = construct_user_created_email_body(user)

    signature = '<p style="float:right">jumpserver</p>'
    if settings.EMAIL_CUSTOM_USER_CREATED_SIGNATURE:
        signature = '<p style="float:right">' + settings.EMAIL_CUSTOM_USER_CREATED_SIGNATURE + '</p>'

    message = honorific + body + signature
    if settings.DEBUG:
        try:
            print(message)
        except OSError:
            pass

    send_mail_async.delay(subject, message, recipient_list, html_message=message)


def get_user_or_pre_auth_user(request):
    user = request.user
    if user.is_authenticated:
        return user
    pre_auth_user_id = request.session.get('user_id')
    user = None
    if pre_auth_user_id:
        user = get_object_or_none(User, pk=pre_auth_user_id)
    return user


def redirect_user_first_login_or_index(request, redirect_field_name):
    # if request.user.is_first_login:
    #     return reverse('authentication:user-first-login')
    url_in_post = request.POST.get(redirect_field_name)
    if url_in_post:
        return url_in_post
    url_in_get = request.GET.get(redirect_field_name, reverse('index'))
    return url_in_get


def generate_otp_uri(username, otp_secret_key=None, issuer="JumpServer"):
    if otp_secret_key is None:
        otp_secret_key = base64.b32encode(os.urandom(10)).decode('utf-8')
    totp = pyotp.TOTP(otp_secret_key)
    otp_issuer_name = settings.OTP_ISSUER_NAME or issuer
    uri = totp.provisioning_uri(name=username, issuer_name=otp_issuer_name)
    return uri, otp_secret_key


def check_otp_code(otp_secret_key, otp_code):
    if not otp_secret_key or not otp_code:
        return False
    totp = pyotp.TOTP(otp_secret_key)
    otp_valid_window = settings.OTP_VALID_WINDOW or 0
    return totp.verify(otp=otp_code, valid_window=otp_valid_window)


def get_password_check_rules(user):
    check_rules = []
    for rule in settings.SECURITY_PASSWORD_RULES:
        key = "id_{}".format(rule.lower())
        if user.is_org_admin and rule == 'SECURITY_PASSWORD_MIN_LENGTH':
            rule = 'SECURITY_ADMIN_USER_PASSWORD_MIN_LENGTH'
        value = getattr(settings, rule)
        if not value:
            continue
        check_rules.append({'key': key, 'value': int(value)})
    return check_rules


def check_password_rules(password, is_org_admin=False):
    pattern = r"^"
    if settings.SECURITY_PASSWORD_UPPER_CASE:
        pattern += '(?=.*[A-Z])'
    if settings.SECURITY_PASSWORD_LOWER_CASE:
        pattern += '(?=.*[a-z])'
    if settings.SECURITY_PASSWORD_NUMBER:
        pattern += '(?=.*\d)'
    if settings.SECURITY_PASSWORD_SPECIAL_CHAR:
        pattern += '(?=.*[`~!@#\$%\^&\*\(\)-=_\+\[\]\{\}\|;:\'\",\.<>\/\?])'
    pattern += '[a-zA-Z\d`~!@#\$%\^&\*\(\)-=_\+\[\]\{\}\|;:\'\",\.<>\/\?]'
    if is_org_admin:
        min_length = settings.SECURITY_ADMIN_USER_PASSWORD_MIN_LENGTH
    else:
        min_length = settings.SECURITY_PASSWORD_MIN_LENGTH
    pattern += '.{' + str(min_length-1) + ',}$'
    match_obj = re.match(pattern, password)
    return bool(match_obj)


class BlockUtil:
    BLOCK_KEY_TMPL: str

    def __init__(self, username):
        self.block_key = self.BLOCK_KEY_TMPL.format(username)
        self.key_ttl = int(settings.SECURITY_LOGIN_LIMIT_TIME) * 60

    def block(self):
        cache.set(self.block_key, True, self.key_ttl)

    def is_block(self):
        return bool(cache.get(self.block_key))


class BlockUtilBase:
    LIMIT_KEY_TMPL: str
    BLOCK_KEY_TMPL: str

    def __init__(self, username, ip):
        self.username = username
        self.ip = ip
        self.limit_key = self.LIMIT_KEY_TMPL.format(username, ip)
        self.block_key = self.BLOCK_KEY_TMPL.format(username)
        self.key_ttl = int(settings.SECURITY_LOGIN_LIMIT_TIME) * 60

    def get_remainder_times(self):
        times_up = settings.SECURITY_LOGIN_LIMIT_COUNT
        times_failed = self.get_failed_count()
        times_remainder = int(times_up) - int(times_failed)
        return times_remainder

    def incr_failed_count(self):
        limit_key = self.limit_key
        count = cache.get(limit_key, 0)
        count += 1
        cache.set(limit_key, count, self.key_ttl)

        limit_count = settings.SECURITY_LOGIN_LIMIT_COUNT
        if count >= limit_count:
            cache.set(self.block_key, True, self.key_ttl)

    def get_failed_count(self):
        count = cache.get(self.limit_key, 0)
        return count

    def clean_failed_count(self):
        cache.delete(self.limit_key)
        cache.delete(self.block_key)

    @classmethod
    def unblock_user(cls, username):
        key_limit = cls.LIMIT_KEY_TMPL.format(username, '*')
        key_block = cls.BLOCK_KEY_TMPL.format(username)
        # Redis 尽量不要用通配
        cache.delete_pattern(key_limit)
        cache.delete(key_block)

    @classmethod
    def is_user_block(cls, username):
        block_key = cls.BLOCK_KEY_TMPL.format(username)
        return bool(cache.get(block_key))

    def is_block(self):
        return bool(cache.get(self.block_key))


class LoginBlockUtil(BlockUtilBase):
    LIMIT_KEY_TMPL = "_LOGIN_LIMIT_{}_{}"
    BLOCK_KEY_TMPL = "_LOGIN_BLOCK_{}"


class MFABlockUtils(BlockUtilBase):
    LIMIT_KEY_TMPL = "_MFA_LIMIT_{}_{}"
    BLOCK_KEY_TMPL = "_MFA_BLOCK_{}"


def construct_user_email(username, email):
    if '@' not in email:
        if '@' in username:
            email = username
        else:
            email = '{}@{}'.format(username, settings.EMAIL_SUFFIX)
    return email


def get_current_org_members(exclude=()):
    from orgs.utils import current_org
    return current_org.get_members(exclude=exclude)


def is_auth_time_valid(session, key):
    return True if session.get(key, 0) > time.time() else False


def is_auth_password_time_valid(session):
    return is_auth_time_valid(session, 'auth_password_expired_at')


def is_auth_otp_time_valid(session):
    return is_auth_time_valid(session, 'auth_opt_expired_at')
