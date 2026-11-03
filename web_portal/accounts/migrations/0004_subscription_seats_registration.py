import decimal
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


def migrate_legacy_accounts(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    PortalUser = apps.get_model("accounts", "PortalUser")
    Organization.objects.filter(name__startswith="Personal workspace ·").update(access_type="individual")
    PortalUser.objects.filter(is_staff=True, is_superuser=False).update(role="organization_admin")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_alter_portaluser_email_alter_portaluser_username"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="access_type",
            field=models.CharField(
                choices=[("individual", "Individual"), ("organization", "Organization")],
                default="organization", max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="organization",
            name="name",
            field=models.CharField(max_length=160),
        ),
        migrations.AddField(
            model_name="portaluser",
            name="role",
            field=models.CharField(
                choices=[("organization_admin", "Organization admin"), ("member", "Member")],
                default="member", max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="portaluser",
            name="trial_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="portaluser",
            name="trial_ends_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("billing_interval", models.CharField(choices=[("monthly", "Monthly"), ("quarterly", "Quarterly"), ("annual", "Annually")], max_length=12)),
                ("price_per_seat", models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(decimal.Decimal("0"))])),
                ("discount_percent", models.DecimalField(decimal_places=2, default=decimal.Decimal("0"), max_digits=5, validators=[MinValueValidator(decimal.Decimal("0")), MaxValueValidator(decimal.Decimal("100"))])),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["billing_interval", "name"]},
        ),
        migrations.CreateModel(
            name="SeatPurchase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seat_count", models.PositiveIntegerField()),
                ("starts_at", models.DateField()),
                ("ends_at", models.DateField()),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("total_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("status", models.CharField(choices=[("completed", "Completed (simulated)"), ("cancelled", "Cancelled")], default="completed", max_length=12)),
                ("payment_mode", models.CharField(default="simulation", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="seat_purchases", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="seat_purchases", to="accounts.organization")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="seat_purchases", to="accounts.subscriptionplan")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="UserSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("starts_at", models.DateField()),
                ("ends_at", models.DateField()),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="accounts.organization")),
                ("purchase", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assignments", to="accounts.seatpurchase")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-starts_at", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="usersubscription",
            constraint=models.UniqueConstraint(fields=("purchase", "user"), name="unique_purchase_user_assignment"),
        ),
        migrations.CreateModel(
            name="ActivePortalSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(max_length=40, unique=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="active_portal_session", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="RegistrationIntent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(max_length=254)),
                ("individual_name", models.CharField(blank=True, max_length=160)),
                ("access_type", models.CharField(choices=[("individual", "Individual"), ("organization", "Organization")], max_length=16)),
                ("organization_name", models.CharField(blank=True, max_length=160)),
                ("seat_count", models.PositiveIntegerField(default=1)),
                ("simulated_total", models.DecimalField(decimal_places=2, default=decimal.Decimal("0"), max_digits=12)),
                ("is_trial", models.BooleanField(default=False)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("plan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="accounts.subscriptionplan")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="subscriptionplan",
            constraint=models.UniqueConstraint(fields=("name", "billing_interval"), name="unique_plan_interval"),
        ),
        migrations.RunPython(migrate_legacy_accounts, migrations.RunPython.noop),
    ]
