from django.db import migrations, models


def designate_existing_portal_admins(apps, schema_editor):
    PortalUser = apps.get_model("accounts", "PortalUser")
    PortalUser.objects.filter(is_staff=True, is_superuser=False).update(is_portal_admin=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_subscription_seats_registration"),
    ]

    operations = [
        migrations.AddField(
            model_name="portaluser",
            name="is_portal_admin",
            field=models.BooleanField(
                default=False,
                help_text="Internal portal administrator; bypasses subscription and trial expiry.",
            ),
        ),
        migrations.RunPython(designate_existing_portal_admins, migrations.RunPython.noop),
    ]
