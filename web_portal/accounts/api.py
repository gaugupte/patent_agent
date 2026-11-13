import json
import logging
import secrets
import re
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import ActivePortalSession, EmailLoginCode, ExternalIdentity, Organization, PortalUser, SeatPurchase

logger = logging.getLogger(__name__)
GOOGLE_ISSUER = "https://accounts.google.com"


def _json_body(request):
    try:
        body = json.loads(request.body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return body if isinstance(body, dict) else None


def _has_active_portal_session(request, user):
    return bool(request.session.session_key and ActivePortalSession.objects.filter(
        user=user, session_key=request.session.session_key
    ).exists())


def _individual_uses_password_login(user):
    return bool(
        user.organization_id
        and user.organization.access_type == Organization.AccessType.INDIVIDUAL
        and user.has_usable_password()
    )


def portal_login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({"detail": "Sign in is required."}, status=401)
        if not _has_active_portal_session(request, user):
            logout(request)
            return JsonResponse({"detail": "Your session is no longer active. Please sign in again."}, status=401)
        if user.is_superuser:
            return JsonResponse({"detail": "Use the administration site for this account."}, status=403)
        if not user.is_active or not user.organization_id or not user.organization.is_active:
            logout(request)
            return JsonResponse({"detail": "This account is not assigned to an active organization."}, status=403)
        today = timezone.localdate()
        has_subscription = user.subscriptions.filter(
            starts_at__lte=today,
            ends_at__gte=today,
            released_at__isnull=True,
            purchase__status=SeatPurchase.Status.COMPLETED,
        ).exists()
        trial_active = bool(user.trial_ends_at and user.trial_ends_at > timezone.now())
        if not user.is_portal_admin and not has_subscription and not trial_active:
            return JsonResponse({"detail": "Your seven-day trial has ended. Choose a plan and complete paid registration to continue."}, status=403)
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

    if not _login_single_session(request, user):
        return JsonResponse({"detail": "This account is already signed in on another browser or device. Sign out there before trying again."}, status=409)
    return _user_payload(user)


def _login_single_session(request, user):
    """Reject a second live portal session; discard stale session records."""
    with transaction.atomic():
        PortalUser.objects.select_for_update().get(pk=user.pk)
        active = ActivePortalSession.objects.select_for_update().filter(user=user).first()
        if active:
            if request.user.is_authenticated and request.user.pk == user.pk and request.session.session_key == active.session_key:
                return True
            existing = Session.objects.filter(session_key=active.session_key, expire_date__gt=timezone.now()).first()
            decoded = existing.get_decoded() if existing else {}
            if str(decoded.get("_auth_user_id", "")) == str(user.pk):
                return False
            active.delete()

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session.save()
        ActivePortalSession.objects.update_or_create(user=user, defaults={"session_key": request.session.session_key})
        return True


def _user_payload(user):
    today = timezone.localdate()
    subscription = user.subscriptions.filter(
        starts_at__lte=today,
        ends_at__gte=today,
        released_at__isnull=True,
        purchase__status=SeatPurchase.Status.COMPLETED,
    ).select_related("purchase__plan").order_by("-ends_at", "-created_at").first()
    trial_active = bool(user.trial_ends_at and user.trial_ends_at > timezone.now())
    return JsonResponse({
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "password_login_enabled": user.has_usable_password(),
        "role": user.role,
        "is_portal_admin": user.is_portal_admin,
        "subscription_active": subscription is not None,
        "trial_active": trial_active,
        "trial_started_at": user.trial_started_at.isoformat() if user.trial_started_at else None,
        "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        "access_active": user.is_portal_admin or subscription is not None or trial_active,
        "subscription_ends_at": subscription.ends_at.isoformat() if subscription else None,
        "organization": {"id": str(user.organization_id), "name": user.organization.name, "access_type": user.organization.access_type},
    })


def _frontend_redirect(path, params=None):
    base = settings.PORTAL_FRONTEND_URL.rstrip("/")
    target = f"{base}/{path.lstrip('/')}"
    return target + ("?" + urlencode(params) if params else "")


def _username_for_email(email):
    stem = re.sub(r"[^A-Za-z0-9_]", "", email.split("@", 1)[0])[:10] or "user"
    for _ in range(20):
        candidate = f"{stem}{secrets.randbelow(1_000_000):06d}"[:16]
        if not PortalUser.objects.filter(username=candidate).exists():
            return candidate
    raise RuntimeError("Could not allocate a username.")


@require_POST
def request_email_code(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)
    email = str(body.get("email", "")).strip().lower()
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Enter a valid email address."}, status=400)

    existing_users = PortalUser.objects.filter(email__iexact=email).select_related("organization")[:2]
    if any(_individual_uses_password_login(user) for user in existing_users):
        return JsonResponse({"detail": "Google and email-code sign-in are for the free trial. Paid individual accounts must sign in with their username and password."}, status=403)

    now = timezone.now()
    ip = request.META.get("REMOTE_ADDR")
    if ip and EmailLoginCode.objects.filter(request_ip=ip, created_at__gt=now - timedelta(hours=1)).count() >= 10:
        return JsonResponse({"detail": "Too many code requests. Try again later."}, status=429)

    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = EmailLoginCode.objects.create(
        email=email, code_hash=make_password(code), expires_at=now + timedelta(minutes=10), request_ip=ip
    )
    try:
        send_mail(
            subject="Your PatentDesk sign-in code",
            message=f"Your PatentDesk verification code is {code}. It expires in 10 minutes. If you did not request it, you can ignore this email.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        challenge.delete()
        logger.exception("Could not send a portal sign-in code")
        return JsonResponse({"detail": "The email could not be sent. Please try again later."}, status=503)
    # A newly issued code replaces any earlier pending code for this address.
    EmailLoginCode.objects.filter(email__iexact=email, consumed_at__isnull=True).exclude(pk=challenge.pk).update(consumed_at=now)
    return JsonResponse({"detail": "If the address can be used, a verification code has been sent."})


@require_POST
def verify_email_code(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)
    email = str(body.get("email", "")).strip().lower()
    code = str(body.get("code", "")).strip()
    challenge = EmailLoginCode.objects.filter(email__iexact=email, consumed_at__isnull=True).order_by("-created_at").first()
    if (not challenge or challenge.expires_at <= timezone.now() or challenge.attempts >= 5
            or not re.fullmatch(r"\d{6}", code)):
        return JsonResponse({"detail": "That code is invalid or has expired. Request a new one."}, status=400)
    challenge.attempts += 1
    challenge.save(update_fields=["attempts"])
    if not check_password(code, challenge.code_hash):
        return JsonResponse({"detail": "That code is incorrect."}, status=400)
    registration_id = str(body.get("registration_intent", "")).strip()
    if registration_id:
        from .billing import complete_registration
        from .models import RegistrationIntent
        intent = RegistrationIntent.objects.filter(pk=registration_id, email__iexact=email).first()
        if intent is None:
            return JsonResponse({"detail": "Registration details were not found. Start registration again."}, status=400)
        requires_password_login = not intent.is_trial
        if requires_password_login:
            pending = request.session.get("validated_password_registration")
            if not isinstance(pending, dict) or pending.get("intent_id") != str(intent.pk) or pending.get("email") != email:
                return JsonResponse({"detail": "Your registration details expired. Start registration again."}, status=400)
            try:
                user = complete_registration(
                    intent,
                    email,
                    username=pending.get("username", ""),
                    password_hash=pending.get("password_hash", ""),
                )
            except ValueError as exc:
                return JsonResponse({"detail": str(exc)}, status=409)
            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at"])
            request.session.pop("validated_password_registration", None)
            if not _login_single_session(request, user):
                return JsonResponse({"detail": "Your account was created. Sign in with your username and password."}, status=409)
            return _user_payload(user)
        try:
            user = complete_registration(intent, email)
        except ValueError as exc:
            return JsonResponse({"detail": str(exc)}, status=409)
        challenge.consumed_at = timezone.now()
        challenge.save(update_fields=["consumed_at"])
        if not _login_single_session(request, user):
            return JsonResponse({"detail": "This account is already signed in on another browser or device. Sign out there before trying again."}, status=409)
        return _user_payload(user)

    users = PortalUser.objects.filter(email__iexact=email).select_related("organization")
    if users.count() > 1:
        return JsonResponse({"detail": "This email is associated with multiple accounts. Contact your administrator."}, status=409)
    user = users.first()
    if user is None:
        return JsonResponse({"detail": "No account uses this email yet. Choose Individual or Organization access on the registration page first."}, status=404)
    elif user.is_superuser:
        return JsonResponse({"detail": "Use the administration site for this account."}, status=403)
    elif not user.is_active or not user.organization_id or not user.organization.is_active:
        return JsonResponse({"detail": "This account is not assigned to an active organization."}, status=403)
    elif _individual_uses_password_login(user):
        return JsonResponse({"detail": "Google and email-code sign-in are for the free trial. Paid individual accounts must sign in with their username and password."}, status=403)
    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=["consumed_at"])
    if not _login_single_session(request, user):
        return JsonResponse({"detail": "This account is already signed in on another browser or device. Sign out there before trying again."}, status=409)
    return _user_payload(user)


@require_GET
def google_login(request):
    if request.GET.get("registration_intent"):
        return HttpResponseRedirect(_frontend_redirect("/register", {"auth_error": "google_signup_disabled"}))
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
    if not client_id or not getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", ""):
        target = "/register" if request.GET.get("registration_intent") else "/login"
        return HttpResponseRedirect(_frontend_redirect(target, {"auth_error": "google_not_configured"}))
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    registration_id = request.GET.get("registration_intent", "")
    if registration_id:
        from .models import RegistrationIntent
        intent = RegistrationIntent.objects.filter(pk=registration_id, expires_at__gt=timezone.now(), consumed_at__isnull=True).first()
        if intent is None:
            return HttpResponseRedirect(_frontend_redirect("/register", {"auth_error": "registration_expired"}))
        if intent.access_type == Organization.AccessType.INDIVIDUAL and not intent.is_trial:
            return HttpResponseRedirect(_frontend_redirect("/register", {"auth_error": "individual_email_required"}))
        request.session["google_registration_intent"] = registration_id
    request.session["google_oidc_state"] = state
    request.session["google_oidc_nonce"] = nonce
    callback = getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "") or request.build_absolute_uri(reverse("google-callback"))
    params = {
        "client_id": client_id,
        "redirect_uri": callback,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    return HttpResponseRedirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@require_GET
def google_callback(request):
    error = request.GET.get("error")
    state = request.GET.get("state", "")
    expected_state = request.session.pop("google_oidc_state", None)
    nonce = request.session.pop("google_oidc_nonce", None)
    if error or not expected_state or not isinstance(state, str) or not secrets.compare_digest(state, expected_state) or not nonce:
        return HttpResponseRedirect(_frontend_redirect("/login", {"auth_error": "google_failed"}))
    code = request.GET.get("code", "")
    if not code:
        return HttpResponseRedirect(_frontend_redirect("/login", {"auth_error": "google_failed"}))
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "")
    callback = getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "") or request.build_absolute_uri(reverse("google-callback"))
    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={"code": code, "client_id": client_id, "client_secret": client_secret,
                  "redirect_uri": callback, "grant_type": "authorization_code"},
            timeout=15,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token
        claims = id_token.verify_oauth2_token(token_data.get("id_token", ""), GoogleRequest(), client_id)
        if claims.get("iss") not in {GOOGLE_ISSUER, "accounts.google.com"}:
            raise ValueError("Unexpected OIDC issuer")
        if claims.get("nonce") != nonce:
            raise ValueError("OIDC nonce did not match")
        email = str(claims.get("email", "")).strip().lower()
        if not email or claims.get("email_verified") is not True:
            raise ValueError("Google did not provide a verified email")
        subject = str(claims["sub"])
        registration_id = request.session.pop("google_registration_intent", "")
        identity = ExternalIdentity.objects.select_related("user", "user__organization").filter(
            issuer=GOOGLE_ISSUER, subject=subject
        ).first()
        if registration_id:
            from .billing import complete_registration
            from .models import RegistrationIntent
            intent = RegistrationIntent.objects.filter(pk=registration_id, email__iexact=email).first()
            if intent is None:
                return HttpResponseRedirect(_frontend_redirect("/register", {"auth_error": "registration_email_mismatch"}))
            try:
                user = complete_registration(intent, email, claims.get("given_name", ""), claims.get("family_name", ""))
            except ValueError:
                return HttpResponseRedirect(_frontend_redirect("/register", {"auth_error": "registration_conflict"}))
            ExternalIdentity.objects.create(user=user, issuer=GOOGLE_ISSUER, subject=subject, email=email)
        elif identity:
            user = identity.user
            identity.email = email
            identity.save(update_fields=["email"])
            if user.email.lower() != email and not PortalUser.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
                user.email = email
                user.save(update_fields=["email"])
        else:
            matches = list(PortalUser.objects.filter(email__iexact=email).select_related("organization")[:2])
            if len(matches) > 1:
                return HttpResponseRedirect(_frontend_redirect("/login", {"auth_error": "account_conflict"}))
            if matches:
                # Only attach to a single account after Google has verified the exact mailbox.
                user = matches[0]
            else:
                return HttpResponseRedirect(_frontend_redirect("/register", {"auth_error": "registration_required"}))
            if not ExternalIdentity.objects.filter(issuer=GOOGLE_ISSUER, subject=subject).exists():
                ExternalIdentity.objects.create(user=user, issuer=GOOGLE_ISSUER, subject=subject, email=email)
        if user.is_superuser or not user.is_active or not user.organization_id or not user.organization.is_active:
            return HttpResponseRedirect(_frontend_redirect("/login", {"auth_error": "account_inactive"}))
        if _individual_uses_password_login(user):
            return HttpResponseRedirect(_frontend_redirect("/login", {"auth_error": "password_login_required"}))
        if not _login_single_session(request, user):
            return HttpResponseRedirect(_frontend_redirect("/login", {"auth_error": "session_already_active"}))
        return HttpResponseRedirect(_frontend_redirect("/inventions"))
    except Exception:
        logger.exception("Google OIDC sign-in failed")
        return HttpResponseRedirect(_frontend_redirect("/login", {"auth_error": "google_failed"}))


@require_POST
def sign_out(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Sign in is required."}, status=401)
    ActivePortalSession.objects.filter(user=request.user, session_key=request.session.session_key).delete()
    logout(request)
    return JsonResponse({"ok": True})


@require_GET
def current_user(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Sign in is required."}, status=401)
    if request.user.is_superuser:
        return JsonResponse({"detail": "Use the administration site for this account."}, status=403)
    if not request.user.is_active:
        logout(request)
        return JsonResponse({"detail": "This account is inactive."}, status=403)
    if not _has_active_portal_session(request, request.user):
        logout(request)
        return JsonResponse({"detail": "Your session is no longer active. Please sign in again."}, status=401)
    if not request.user.organization_id or not request.user.organization.is_active:
        return JsonResponse({"detail": "This account is not assigned to an active organization."}, status=403)
    today = timezone.localdate()
    subscription = request.user.subscriptions.filter(
        starts_at__lte=today,
        ends_at__gte=today,
        released_at__isnull=True,
        purchase__status=SeatPurchase.Status.COMPLETED,
    ).select_related("purchase__plan").order_by("-ends_at", "-created_at").first()
    trial_active = bool(request.user.trial_ends_at and request.user.trial_ends_at > timezone.now())
    return JsonResponse(
        {
            "id": request.user.pk,
            "username": request.user.username,
            "email": request.user.email,
            "password_login_enabled": request.user.has_usable_password(),
            "role": request.user.role,
            "is_portal_admin": request.user.is_portal_admin,
            "subscription_active": subscription is not None,
            "trial_active": trial_active,
            "trial_started_at": request.user.trial_started_at.isoformat() if request.user.trial_started_at else None,
            "trial_ends_at": request.user.trial_ends_at.isoformat() if request.user.trial_ends_at else None,
            "access_active": request.user.is_portal_admin or subscription is not None or trial_active,
            "subscription_ends_at": subscription.ends_at.isoformat() if subscription else None,
            "organization": {
                "id": str(request.user.organization_id),
                "name": request.user.organization.name,
                "access_type": request.user.organization.access_type,
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
