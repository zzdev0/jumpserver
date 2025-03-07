from importlib import import_module

from django.conf import settings
from django.contrib.auth import user_logged_in
from django.core.cache import cache
from django.dispatch import receiver
from django_cas_ng.signals import cas_user_authenticated

from jms_oidc_rp.signals import openid_user_login_failed, openid_user_login_success

from .signals import post_auth_success, post_auth_failed


@receiver(user_logged_in)
def on_user_auth_login_success(sender, user, request, **kwargs):
    # 开启了 MFA，且没有校验过

    if user.mfa_enabled and not settings.OTP_IN_RADIUS and not request.session.get('auth_mfa'):
        request.session['auth_mfa_required'] = 1

    if settings.USER_LOGIN_SINGLE_MACHINE_ENABLED:
        user_id = 'single_machine_login_' + str(user.id)
        session_key = cache.get(user_id)
        if session_key and session_key != request.session.session_key:
            session = import_module(settings.SESSION_ENGINE).SessionStore(session_key)
            session.delete()
        cache.set(user_id, request.session.session_key, None)


@receiver(openid_user_login_success)
def on_oidc_user_login_success(sender, request, user, create=False, **kwargs):
    request.session['auth_backend'] = settings.AUTH_BACKEND_OIDC_CODE
    post_auth_success.send(sender, user=user, request=request)


@receiver(openid_user_login_failed)
def on_oidc_user_login_failed(sender, username, request, reason, **kwargs):
    request.session['auth_backend'] = settings.AUTH_BACKEND_OIDC_CODE
    post_auth_failed.send(sender, username=username, request=request, reason=reason)


@receiver(cas_user_authenticated)
def on_cas_user_login_success(sender, request, user, **kwargs):
    request.session['auth_backend'] = settings.AUTH_BACKEND_CAS
    post_auth_success.send(sender, user=user, request=request)
