from django.db import migrations, models


def forwards(apps, schema_editor):
    ShopUser = apps.get_model("accounts", "ShopUser")

    for user in ShopUser.objects.all().only(
        "id",
        "two_factor_enabled",
        "two_factor_method",
        "two_factor_totp_enabled",
        "two_factor_email_enabled",
    ):
        if user.two_factor_enabled:
            if user.two_factor_method == "email_code":
                user.two_factor_email_enabled = True
            else:
                user.two_factor_totp_enabled = True
            ShopUser.objects.filter(pk=user.pk).update(
                two_factor_totp_enabled=user.two_factor_totp_enabled,
                two_factor_email_enabled=user.two_factor_email_enabled,
            )


def backwards(apps, schema_editor):
    ShopUser = apps.get_model("accounts", "ShopUser")

    for user in ShopUser.objects.all().only(
        "id",
        "two_factor_totp_enabled",
        "two_factor_email_enabled",
    ):
        enabled = bool(user.two_factor_totp_enabled or user.two_factor_email_enabled)
        method = "totp"
        if user.two_factor_email_enabled and not user.two_factor_totp_enabled:
            method = "email_code"

        ShopUser.objects.filter(pk=user.pk).update(
            two_factor_enabled=enabled,
            two_factor_method=method,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_shopuser_contact_unique_human_id_email2fa"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopuser",
            name="two_factor_email_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="shopuser",
            name="two_factor_totp_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(forwards, backwards),
    ]
