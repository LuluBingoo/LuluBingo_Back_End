from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0003_transaction_actor_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="currency",
            field=models.CharField(
                choices=[("ETB", "ETB")],
                default="ETB",
                max_length=10,
            ),
        ),
    ]
