from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "tx_type", "-created_at"],
                name="tx_user_type_created_idx",
            ),
        ),
    ]
