from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0012_unbounded_players_and_default_bet"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="is_paused",
            field=models.BooleanField(default=False),
        ),
    ]
