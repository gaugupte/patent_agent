from django.urls import path

from . import api


urlpatterns = [
    path("login/", api.sign_in, name="portal-login"),
    path("email-code/request/", api.request_email_code, name="email-code-request"),
    path("email-code/verify/", api.verify_email_code, name="email-code-verify"),
    path("google/login/", api.google_login, name="google-login"),
    path("google/callback/", api.google_callback, name="google-callback"),
    path("logout/", api.sign_out, name="portal-logout"),
    path("me/", api.current_user, name="portal-current-user"),
    path("password-reset/", api.request_password_reset, name="portal-password-reset"),
    path("password-reset/confirm/", api.confirm_password_reset, name="portal-password-reset-confirm"),
]
