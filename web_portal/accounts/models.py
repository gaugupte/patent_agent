import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Organization(models.Model):
    class AccessType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        ORGANIZATION = "organization", "Organization"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    access_type = models.CharField(max_length=16, choices=AccessType.choices, default=AccessType.ORGANIZATION)
    address = models.TextField(blank=True)
    contact_person = models.CharField(max_length=160, blank=True)
    subscription_type = models.CharField(max_length=80, blank=True)
    starts_at = models.DateField(null=True, blank=True)
    ends_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PortalUser(AbstractUser):
    class Role(models.TextChoices):
        ORGANIZATION_ADMIN = "organization_admin", "Organization admin"
        MEMBER = "member", "Member"

    username = models.CharField(max_length=16, unique=True)
    email = models.EmailField()
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.MEMBER)
    is_portal_admin = models.BooleanField(
        default=False,
        help_text="Internal portal administrator; bypasses subscription and trial expiry.",
    )
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
    )

    def clean(self):
        super().clean()
        if not self.is_superuser and self.organization_id is None:
            from django.core.exceptions import ValidationError

            raise ValidationError({"organization": "Portal users must belong to an organization."})

    def __str__(self) -> str:
        return self.username


class SubscriptionPlan(models.Model):
    class BillingInterval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUAL = "annual", "Annually"

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    billing_interval = models.CharField(max_length=12, choices=BillingInterval.choices)
    price_per_seat = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["billing_interval", "name"]
        constraints = [models.UniqueConstraint(fields=("name", "billing_interval"), name="unique_plan_interval")]

    @property
    def discounted_price(self):
        return (self.price_per_seat * (Decimal("100") - self.discount_percent) / Decimal("100")).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.name} ({self.get_billing_interval_display()})"


class SeatPurchase(models.Model):
    """A simulated purchase that grants a fixed number of seats for a plan term."""

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed (simulated)"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="seat_purchases")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="seat_purchases")
    seat_count = models.PositiveIntegerField()
    starts_at = models.DateField()
    ends_at = models.DateField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.COMPLETED)
    payment_mode = models.CharField(max_length=16, default="simulation")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="seat_purchases")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.organization}: {self.seat_count} {self.plan} seats through {self.ends_at}"


class UserSubscription(models.Model):
    """Assigns one purchased seat and its validity dates to a portal user."""

    purchase = models.ForeignKey(SeatPurchase, on_delete=models.PROTECT, related_name="assignments")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="subscriptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscriptions")
    starts_at = models.DateField()
    ends_at = models.DateField()
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at", "-created_at"]
        constraints = [models.UniqueConstraint(fields=("purchase", "user"), name="unique_purchase_user_assignment")]

    def __str__(self):
        return f"{self.user} — {self.purchase.plan} through {self.ends_at}"


class ActivePortalSession(models.Model):
    """Tracks the one browser session currently allowed for a portal user."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="active_portal_session")
    session_key = models.CharField(max_length=40, unique=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Active portal session for {self.user}"


class RegistrationIntent(models.Model):
    """Short-lived onboarding choice retained while the user verifies identity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    individual_name = models.CharField(max_length=160, blank=True)
    access_type = models.CharField(max_length=16, choices=Organization.AccessType.choices)
    organization_name = models.CharField(max_length=160, blank=True)
    plan = models.ForeignKey(SubscriptionPlan, null=True, blank=True, on_delete=models.PROTECT)
    seat_count = models.PositiveIntegerField(default=1)
    simulated_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    is_trial = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ExternalIdentity(models.Model):
    """A verified external login identity, keyed by provider issuer and subject."""

    user = models.ForeignKey(PortalUser, on_delete=models.CASCADE, related_name="external_identities")
    issuer = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("issuer", "subject"), name="unique_external_identity")]


class EmailLoginCode(models.Model):
    """Short-lived, single-use email verification/login challenge."""

    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("email", "created_at"), name="accounts_em_email_1e2b18_idx")]
