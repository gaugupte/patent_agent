import json
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import PortalUser


def _json_body(request):
    try:
        body = json.loads(request.body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return body if isinstance(body, dict) else None


def portal_login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({"detail": "Sign in is required."}, status=401)
        if user.is_superuser:
            return JsonResponse({"detail": "Use the administration site for this account."}, status=403)
        if not user.is_active or not user.organization_id or not user.organization.is_active:
            logout(request)
            return JsonResponse({"detail": "This account is not assigned to an active organization."}, status=403)
        return view(request, *args, **kwargs)

    return wrapped


@require_GET
def health(_request):
    return JsonResponse({"status": "ok"})


@ensure_csrf_cookie
@require_GET
def csrf_token(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_POST
def sign_in(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)

    user = authenticate(
        request,
        username=str(body.get("username", "")).strip(),
        password=str(body.get("password", "")),
    )
    if user is None:
        return JsonResponse({"detail": "The username or password is incorrect."}, status=400)
    if user.is_superuser:
        return JsonResponse({"detail": "Use the administration site for this account."}, status=403)
    if not user.organization_id or not user.organization.is_active:
        return JsonResponse({"detail": "This account is not assigned to an active organization."}, status=403)

    login(request, user)
    return JsonResponse(
        {
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "organization": {"id": str(user.organization_id), "name": user.organization.name},
        }
    )


@require_POST
@portal_login_required
def sign_out(request):
    logout(request)
    return JsonResponse({"ok": True})


@require_GET
def current_user(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Sign in is required."}, status=401)
    if request.user.is_superuser:
        return JsonResponse({"detail": "Use the administration site for this account."}, status=403)
    if not request.user.organization_id or not request.user.organization.is_active:
        return JsonResponse({"detail": "This account is not assigned to an active organization."}, status=403)
    return JsonResponse(
        {
            "id": request.user.pk,
            "username": request.user.username,
            "email": request.user.email,
            "organization": {
                "id": str(request.user.organization_id),
                "name": request.user.organization.name,
            },
        }
    )


@require_POST
def request_password_reset(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)
    form = PasswordResetForm({"email": str(body.get("email", "")).strip()})
    if form.is_valid():
        form.save(
            request=request,
            use_https=request.is_secure(),
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
        )
    # Keep the response identical for known and unknown addresses.
    return JsonResponse({"detail": "If that email belongs to an account, a reset link has been sent."})


@require_POST
def confirm_password_reset(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)
    try:
        uid = force_str(urlsafe_base64_decode(str(body.get("uid", ""))))
        user = PortalUser.objects.get(pk=uid, is_active=True)
    except (TypeError, ValueError, OverflowError, PortalUser.DoesNotExist):
        user = None
    if user is None or not default_token_generator.check_token(user, str(body.get("token", ""))):
        return JsonResponse({"detail": "This password reset link is invalid or has expired."}, status=400)

    form = SetPasswordForm(
        user,
        {
            "new_password1": str(body.get("password", "")),
            "new_password2": str(body.get("password_confirmation", "")),
        },
    )
    if not form.is_valid():
        return JsonResponse({"detail": " ".join(form.errors.get("new_password2", [])) or "Password does not meet requirements."}, status=400)
    form.save()
    return JsonResponse({"detail": "Password updated. You can now sign in."})
