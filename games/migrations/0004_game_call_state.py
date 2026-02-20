from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0003_shop_bingo_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="call_cursor",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="game",
            name="called_numbers",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="game",
            name="current_called_number",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
