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
