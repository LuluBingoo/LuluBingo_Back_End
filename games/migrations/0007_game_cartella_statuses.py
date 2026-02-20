from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0006_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="cartella_statuses",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
