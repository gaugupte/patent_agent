import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models

import patents.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="customers", to="accounts.organization")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Invention",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inventions_created", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventions", to="patents.customer")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="InventionVersion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("number", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], default="processing", max_length=16)),
                ("idf_file", models.FileField(max_length=500, upload_to=patents.models.idf_upload_path, validators=[django.core.validators.FileExtensionValidator(["txt"])])),
                ("analysis_result", models.JSONField(blank=True, default=dict)),
                ("report_path", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("invention", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versions", to="patents.invention")),
            ],
            options={"ordering": ["-number"]},
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(fields=("organization", "name"), name="unique_customer_name_per_org"),
        ),
        migrations.AddConstraint(
            model_name="inventionversion",
            constraint=models.UniqueConstraint(fields=("invention", "number"), name="unique_invention_version_number"),
        ),
    ]
