import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160, unique=True)
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
    username = models.CharField(max_length=16, unique=True)
    email = models.EmailField()
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
