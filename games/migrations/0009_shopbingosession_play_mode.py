from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0008_game_cut_percentage"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopbingosession",
            name="play_mode",
            field=models.CharField(
                choices=[("online", "Online"), ("offline", "Offline")],
                default="online",
                max_length=20,
            ),
        ),
    ]