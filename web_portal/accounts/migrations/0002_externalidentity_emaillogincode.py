import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="EmailLoginCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("code_hash", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("request_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"indexes": [models.Index(fields=["email", "created_at"], name="accounts_em_email_1e2b18_idx")]},
        ),
        migrations.CreateModel(
            name="ExternalIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("issuer", models.CharField(max_length=255)),
                ("subject", models.CharField(max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="external_identities", to="accounts.portaluser")),
            ],
        ),
        migrations.AddConstraint(
            model_name="externalidentity",
            constraint=models.UniqueConstraint(fields=("issuer", "subject"), name="unique_external_identity"),
        ),
    ]
