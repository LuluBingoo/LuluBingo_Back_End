from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0009_shopbingosession_play_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shopbingosession",
            name="play_mode",
            field=models.CharField(
                choices=[("online", "Online"), ("offline", "Offline")],
                default="offline",
                max_length=20,
            ),
        ),
    ]