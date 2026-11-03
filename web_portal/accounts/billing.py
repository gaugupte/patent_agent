import calendar
from functools import wraps
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .api import _has_active_portal_session, _json_body, _username_for_email
from .models import ActivePortalSession, Organization, PortalUser, RegistrationIntent, SeatPurchase, SubscriptionPlan, UserSubscription


def organization_admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Sign in is required."}, status=401)
        if not _has_active_portal_session(request, request.user):
            return JsonResponse({"detail": "Your session is no longer active. Please sign in again."}, status=401)
        if request.user.is_superuser:
            return JsonResponse({"detail": "Use the administration site for this account."}, status=403)
        if not request.user.is_active or not request.user.organization_id or not request.user.organization.is_active:
            return JsonResponse({"detail": "This account is not assigned to an active organization."}, status=403)
        if request.user.role != PortalUser.Role.ORGANIZATION_ADMIN:
            return JsonResponse({"detail": "Organization administrator access is required."}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def _add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _plan_json(plan):
    return {
        "id": plan.pk,
        "name": plan.name,
        "description": plan.description,
        "billing_interval": plan.billing_interval,
        "billing_interval_label": plan.get_billing_interval_display(),
        "price_per_seat": str(plan.price_per_seat),
        "discount_percent": str(plan.discount_percent),
        "discounted_price": str(plan.discounted_price),
    }


def _current_assignments(purchase):
    return purchase.assignments.filter(released_at__isnull=True).count()


def _subscription_for(user):
    today = timezone.localdate()
    return user.subscriptions.filter(
        starts_at__lte=today,
        ends_at__gte=today,
        released_at__isnull=True,
        purchase__status=SeatPurchase.Status.COMPLETED,
        organization__is_active=True,
    ).select_related("purchase__plan").order_by("-ends_at", "-created_at").first()


@require_GET
def public_plans(_request):
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("billing_interval", "name")
    return JsonResponse({"plans": [_plan_json(plan) for plan in plans]})


@require_POST
def start_registration(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)
    email = str(body.get("email", "")).strip().lower()
    access_type = str(body.get("access_type", "")).strip()
    organization_name = str(body.get("organization_name", "")).strip()
    individual_name = str(body.get("individual_name", "")).strip()
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    password_confirmation = str(body.get("password_confirmation", ""))
    validated_password_hash = ""
    is_trial = body.get("start_trial") is True
    try:
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        validate_email(email)
        if is_trial:
            plan_id, seat_count = None, 1
        else:
            plan_id = int(body.get("plan_id"))
            seat_count = int(body.get("seat_count", 1))
    except (ValidationError, TypeError, ValueError):
        return JsonResponse({"detail": "Enter a valid email and choose a plan and seat count."}, status=400)
    if access_type not in Organization.AccessType.values:
        return JsonResponse({"detail": "Choose individual or organization access first."}, status=400)
    if is_trial and access_type != Organization.AccessType.INDIVIDUAL:
        return JsonResponse({"detail": "The seven-day trial is available for individual accounts."}, status=400)
    if access_type == Organization.AccessType.INDIVIDUAL:
        seat_count = 1
        if not individual_name or len(individual_name) > 160:
            return JsonResponse({"detail": "Enter your name up to 160 characters."}, status=400)
        if not is_trial:
            if not username or len(username) > 16:
                return JsonResponse({"detail": "Choose a username with 1 to 16 characters."}, status=400)
            try:
                PortalUser._meta.get_field("username").run_validators(username)
            except ValidationError as exc:
                return JsonResponse({"detail": " ".join(exc.messages)}, status=400)
            if PortalUser.objects.filter(username__iexact=username).exists():
                return JsonResponse({"detail": "That username is already taken. Choose another."}, status=409)
            if not password:
                return JsonResponse({"detail": "Create a password before requesting the email confirmation code."}, status=400)
            if password != password_confirmation:
                return JsonResponse({"detail": "The password and confirmation do not match."}, status=400)
            name_parts = individual_name.split(maxsplit=1)
            candidate = PortalUser(
                username=username,
                email=email,
                first_name=name_parts[0],
                last_name=name_parts[1] if len(name_parts) > 1 else "",
            )
            try:
                validate_password(password, candidate)
            except ValidationError as exc:
                return JsonResponse({"detail": " ".join(exc.messages)}, status=400)
            # Keep only Django's password hash in the server-side session until email is confirmed.
            validated_password_hash = make_password(password)
    elif not organization_name or len(organization_name) > 160:
        return JsonResponse({"detail": "Enter an organization name up to 160 characters."}, status=400)
    if not 1 <= seat_count <= 500:
        return JsonResponse({"detail": "Choose between 1 and 500 seats."}, status=400)
    if PortalUser.objects.filter(email__iexact=email).exists():
        return JsonResponse({"detail": "An account with this email already exists. Sign in instead."}, status=409)
    if access_type == Organization.AccessType.ORGANIZATION and Organization.objects.filter(name__iexact=organization_name).exists():
        return JsonResponse({"detail": "An organization with that name already exists."}, status=409)
    plan = SubscriptionPlan.objects.filter(pk=plan_id, is_active=True).first() if plan_id else None
    if not is_trial and plan is None:
        return JsonResponse({"detail": "That plan is unavailable."}, status=404)
    if access_type == Organization.AccessType.INDIVIDUAL:
        seat_count = 1
    total = plan.discounted_price * Decimal(seat_count) if plan else Decimal("0")
    intent = RegistrationIntent.objects.create(
        email=email,
        access_type=access_type,
        individual_name=individual_name if access_type == Organization.AccessType.INDIVIDUAL else "",
        organization_name=organization_name if access_type == Organization.AccessType.ORGANIZATION else "",
        plan=plan,
        seat_count=seat_count,
        simulated_total=total,
        is_trial=is_trial,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    if access_type == Organization.AccessType.INDIVIDUAL and not is_trial:
        request.session["validated_paid_registration"] = {
            "intent_id": str(intent.pk),
            "email": email,
            "username": username,
            "password_hash": validated_password_hash,
        }
        request.session.set_expiry(3600)
    else:
        request.session.pop("validated_paid_registration", None)
    return JsonResponse({
        "registration_intent": str(intent.pk),
        "payment_mode": "simulation",
        "total": str(total),
        "detail": "Seven-day trial ready. No payment is required; verify your email or continue with Google to start it." if is_trial else "Test checkout ready. No real payment will be taken. Verify your email to create your account and activate one seat.",
    }, status=201)


def complete_registration(intent, email, first_name="", last_name="", username="", password_hash=""):
    """Consume a verified onboarding intent and create its organization and seats."""
    with transaction.atomic():
        intent = RegistrationIntent.objects.select_for_update().select_related("plan").get(pk=intent.pk)
        if intent.consumed_at or intent.expires_at <= timezone.now():
            raise ValueError("This registration has expired. Start again.")
        if email.lower() != intent.email.lower() or PortalUser.objects.filter(email__iexact=email).exists():
            raise ValueError("An account already exists for this email. Sign in instead.")
        first_name = str(first_name or "")
        last_name = str(last_name or "")
        if intent.access_type == Organization.AccessType.INDIVIDUAL and not (first_name or last_name):
            name_parts = intent.individual_name.split(maxsplit=1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
        now = timezone.now()
        if intent.is_trial and (intent.access_type != Organization.AccessType.INDIVIDUAL or intent.plan_id):
            raise ValueError("This trial registration is invalid. Start again.")
        individual_paid = intent.access_type == Organization.AccessType.INDIVIDUAL and not intent.is_trial
        if individual_paid:
            username = str(username or "").strip()
            if not username or len(username) > 16:
                raise ValueError("Choose a username with 1 to 16 characters.")
            if PortalUser.objects.filter(username__iexact=username).exists():
                raise ValueError("That username is already taken. Choose another.")
            try:
                PortalUser._meta.get_field("username").run_validators(username)
            except ValidationError as exc:
                raise ValueError(" ".join(exc.messages)) from exc
            if not password_hash:
                raise ValueError("Password setup details are missing. Start registration again.")
        user = PortalUser(
            username=username if individual_paid else _username_for_email(email), email=email,
            first_name=first_name[:150], last_name=last_name[:150],
            role=PortalUser.Role.ORGANIZATION_ADMIN,
            trial_started_at=now if intent.is_trial else None,
            trial_ends_at=now + timedelta(days=7) if intent.is_trial else None,
        )
        if individual_paid:
            user.password = password_hash
        else:
            user.set_unusable_password()
        user.save()
        if intent.access_type == Organization.AccessType.INDIVIDUAL:
            org_name = intent.individual_name
        else:
            org_name = intent.organization_name
            if Organization.objects.filter(name__iexact=org_name).exists():
                raise ValueError("An organization with that name already exists. Start again with another name.")
        organization = Organization.objects.create(name=org_name, access_type=intent.access_type)
        user.organization = organization
        user.save(update_fields=["organization"])
        if not intent.is_trial:
            if intent.plan is None:
                raise ValueError("Select a plan before registering.")
            today = timezone.localdate()
            months = {SubscriptionPlan.BillingInterval.MONTHLY: 1,
                      SubscriptionPlan.BillingInterval.QUARTERLY: 3,
                      SubscriptionPlan.BillingInterval.ANNUAL: 12}[intent.plan.billing_interval]
            ends = _add_months(today, months) - timedelta(days=1)
            purchase = SeatPurchase.objects.create(
                organization=organization,
                plan=intent.plan,
                seat_count=intent.seat_count,
                starts_at=today,
                ends_at=ends,
                unit_price=intent.plan.discounted_price,
                total_price=intent.simulated_total,
                status=SeatPurchase.Status.COMPLETED,
                payment_mode="simulation",
                created_by=user,
            )
            UserSubscription.objects.create(
                purchase=purchase, organization=organization, user=user,
                starts_at=today, ends_at=ends,
            )
        intent.consumed_at = timezone.now()
        intent.save(update_fields=["consumed_at"])
        return user


@require_GET
@organization_admin_required
def organization_billing(request):
    org = request.user.organization
    today = timezone.localdate()
    user_subscription = _subscription_for(request.user)
    purchases = list(org.seat_purchases.select_related("plan").order_by("-created_at"))
    current_purchases = [p for p in purchases if p.status == SeatPurchase.Status.COMPLETED and p.starts_at <= today <= p.ends_at]
    seats_total = sum(p.seat_count for p in current_purchases)
    seats_assigned = sum(_current_assignments(p) for p in current_purchases)
    users = org.users.filter(is_superuser=False).order_by("email", "username")
    user_rows = []
    for user in users:
        subscription = _subscription_for(user)
        user_rows.append({
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "plan": _plan_json(subscription.purchase.plan) if subscription else None,
            "starts_at": subscription.starts_at.isoformat() if subscription else None,
            "ends_at": subscription.ends_at.isoformat() if subscription else None,
        })
    return JsonResponse({
        "organization": {"id": str(org.pk), "name": org.name, "access_type": org.access_type},
        "trial_active": bool(request.user.trial_ends_at and request.user.trial_ends_at > timezone.now()),
        "trial_started_at": request.user.trial_started_at.isoformat() if request.user.trial_started_at else None,
        "trial_ends_at": request.user.trial_ends_at.isoformat() if request.user.trial_ends_at else None,
        "subscription_active": user_subscription is not None,
        "subscription_ends_at": user_subscription.ends_at.isoformat() if user_subscription else None,
        "seat_count": seats_total,
        "assigned_seats": seats_assigned,
        "available_seats": max(0, seats_total - seats_assigned),
        "users": user_rows,
        "purchases": [{
            "id": p.pk, "plan": _plan_json(p.plan), "seat_count": p.seat_count,
            "starts_at": p.starts_at.isoformat(), "ends_at": p.ends_at.isoformat(),
            "total_price": str(p.total_price), "status": p.status, "payment_mode": p.payment_mode,
            "assigned": _current_assignments(p),
            "available": max(0, p.seat_count - _current_assignments(p)) if p.status == SeatPurchase.Status.COMPLETED and p.starts_at <= today <= p.ends_at else 0,
        } for p in purchases],
    })


@require_POST
@organization_admin_required
def simulate_seat_purchase(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)
    try:
        plan_id = int(body.get("plan_id"))
        seats = int(body.get("seat_count"))
    except (TypeError, ValueError):
        return JsonResponse({"detail": "Choose a plan and a valid number of seats."}, status=400)
    if not 1 <= seats <= 500:
        return JsonResponse({"detail": "Choose between 1 and 500 seats."}, status=400)
    password_form = None
    if request.user.organization.access_type == Organization.AccessType.INDIVIDUAL:
        seats = 1
        if request.user.trial_ends_at and request.user.trial_ends_at > timezone.now():
            return JsonResponse({"detail": "Your seven-day trial is still active. You can register and choose a paid plan after it ends."}, status=409)
        if not request.user.has_usable_password():
            password_form = SetPasswordForm(request.user, {
                "new_password1": str(body.get("password", "")),
                "new_password2": str(body.get("password_confirmation", "")),
            })
            if not password_form.is_valid():
                return JsonResponse({"detail": " ".join(password_form.errors.get("new_password2", [])) or "Choose a valid matching password."}, status=400)
    plan = SubscriptionPlan.objects.filter(pk=plan_id, is_active=True).first()
    if plan is None:
        return JsonResponse({"detail": "That plan is unavailable."}, status=404)

    starts = timezone.localdate()
    months = {SubscriptionPlan.BillingInterval.MONTHLY: 1,
              SubscriptionPlan.BillingInterval.QUARTERLY: 3,
              SubscriptionPlan.BillingInterval.ANNUAL: 12}[plan.billing_interval]
    ends = _add_months(starts, months) - timedelta(days=1)
    unit_price = plan.discounted_price
    with transaction.atomic():
        purchase = SeatPurchase.objects.create(
            organization=request.user.organization,
            plan=plan,
            seat_count=seats,
            starts_at=starts,
            ends_at=ends,
            unit_price=unit_price,
            total_price=(unit_price * Decimal(seats)).quantize(Decimal("0.01")),
            created_by=request.user,
            payment_mode="simulation",
        )
        # The purchaser is also a portal user, so a new organization purchase
        # allocates one of its seats to the admin. Individual plans always have
        # exactly one seat, assigned to the account owner.
        UserSubscription.objects.create(
            purchase=purchase,
            organization=request.user.organization,
            user=request.user,
            starts_at=starts,
            ends_at=ends,
        )
        if password_form is not None:
            password_form.save()
    if password_form is not None:
        update_session_auth_hash(request, request.user)
        request.session.save()
        ActivePortalSession.objects.filter(user=request.user).update(session_key=request.session.session_key)
    return JsonResponse({
        "detail": "Test purchase simulated successfully. No money was charged. One seat is assigned to your account.",
        "purchase": {"id": purchase.pk, "seat_count": seats, "starts_at": starts.isoformat(), "ends_at": ends.isoformat(), "total_price": str(purchase.total_price), "payment_mode": purchase.payment_mode},
    }, status=201)


@require_POST
@organization_admin_required
def add_organization_user(request):
    if request.user.organization.access_type != Organization.AccessType.ORGANIZATION:
        return JsonResponse({"detail": "Individual plans cannot add organization users."}, status=403)
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)
    email = str(body.get("email", "")).strip().lower()
    requested_purchase_id = str(body.get("purchase_id", "")).strip()
    try:
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Enter a valid email address."}, status=400)
    today = timezone.localdate()
    with transaction.atomic():
        org = Organization.objects.select_for_update().get(pk=request.user.organization_id)
        matching_users = list(PortalUser.objects.select_for_update().filter(email__iexact=email)[:2])
        if len(matching_users) > 1:
            return JsonResponse({"detail": "That email is associated with multiple accounts. Contact support."}, status=409)
        user = matching_users[0] if matching_users else None
        if user and (user.organization_id != org.pk or user.role != PortalUser.Role.MEMBER):
            return JsonResponse({"detail": "That email already belongs to an account outside this organization."}, status=409)
        if user and user.is_active and user.subscriptions.filter(
            starts_at__lte=today, ends_at__gte=today, released_at__isnull=True,
            purchase__status=SeatPurchase.Status.COMPLETED,
        ).exists():
            return JsonResponse({"detail": "That user already has an active seat."}, status=409)
        purchase_qs = SeatPurchase.objects.select_for_update().filter(
            organization=org, status=SeatPurchase.Status.COMPLETED,
            starts_at__lte=today, ends_at__gte=today,
        )
        if requested_purchase_id:
            try:
                purchase_qs = purchase_qs.filter(pk=int(requested_purchase_id))
            except ValueError:
                return JsonResponse({"detail": "Choose a valid seat purchase."}, status=400)
        purchases = list(purchase_qs.select_related("plan").order_by("ends_at", "created_at"))
        available = next((p for p in purchases if _current_assignments(p) < p.seat_count), None)
        if available is None:
            return JsonResponse({"detail": "No unassigned active seats are available. Simulate a seat purchase before adding users."}, status=409)
        if user is None:
            user = PortalUser(
                username=_username_for_email(email), email=email, organization=org,
                role=PortalUser.Role.MEMBER, is_active=True,
            )
            user.set_unusable_password()
            user.save()
        else:
            user.is_active = True
            user.save(update_fields=["is_active"])
        UserSubscription.objects.create(
            purchase=available,
            organization=org,
            user=user,
            starts_at=max(available.starts_at, today),
            ends_at=available.ends_at,
        )
    return JsonResponse({"user": {"id": user.pk, "username": user.username, "email": user.email, "ends_at": available.ends_at.isoformat()}}, status=201)


@require_POST
@organization_admin_required
def remove_organization_user(request, user_id):
    if request.user.organization.access_type != Organization.AccessType.ORGANIZATION:
        return JsonResponse({"detail": "Individual plans do not have organization members."}, status=403)
    with transaction.atomic():
        user = PortalUser.objects.select_for_update().filter(
            pk=user_id, organization=request.user.organization,
            role=PortalUser.Role.MEMBER, is_active=True,
        ).first()
        if user is None:
            return JsonResponse({"detail": "Active organization member not found."}, status=404)
        user.is_active = False
        user.save(update_fields=["is_active"])
        ActivePortalSession.objects.filter(user=user).delete()
        UserSubscription.objects.filter(user=user, released_at__isnull=True).update(released_at=timezone.now())
    return JsonResponse({"ok": True, "detail": "User access was disabled and the assigned seat released."})
