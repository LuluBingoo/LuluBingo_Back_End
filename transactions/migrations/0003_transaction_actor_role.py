from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0002_transaction_perf_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="actor_role",
            field=models.CharField(
                choices=[("shop", "Shop"), ("admin", "Admin"), ("system", "System")],
                default="shop",
                max_length=20,
            ),
        ),
    ]
