import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

from accounts.models import Organization


def idf_upload_path(instance, filename: str) -> str:
    safe_name = os.path.basename(filename) or "invention.txt"
    organization_id = instance.invention.customer.organization_id
    return (
        f"organizations/{organization_id}/inventions/{instance.invention_id}/"
        f"versions/{instance.number}/{safe_name}"
    )


class Customer(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="customers")
    name = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="unique_customer_name_per_org")
        ]

    def __str__(self) -> str:
        return self.name


class Invention(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="inventions")
    title = models.CharField(max_length=20)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="inventions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def invention_number(self) -> str:
        return f"INV-{self.pk:06d}" if self.pk else "Pending"

    @property
    def organization(self) -> Organization:
        return self.customer.organization

    def __str__(self) -> str:
        return f"{self.invention_number}: {self.title}"


class InventionVersion(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invention = models.ForeignKey(Invention, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROCESSING)
    idf_file = models.FileField(
        upload_to=idf_upload_path,
        validators=[FileExtensionValidator(["txt"])],
        max_length=500,
    )
    analysis_result = models.JSONField(default=dict, blank=True)
    report_path = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["invention", "number"], name="unique_invention_version_number")
        ]

    @property
    def idf_filename(self) -> str:
        return Path(self.idf_file.name).name if self.idf_file else ""

    def __str__(self) -> str:
        return f"{self.invention.invention_number} v{self.number}"
