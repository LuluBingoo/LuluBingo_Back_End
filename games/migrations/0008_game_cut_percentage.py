from django.db import migrations, models


def forwards(apps, schema_editor):
    Game = apps.get_model("games", "Game")

    for game in Game.objects.all().only("id", "win_percentage"):
        win_percentage = game.win_percentage if game.win_percentage is not None else 90
        try:
            win_percentage_value = float(win_percentage)
        except (TypeError, ValueError):
            win_percentage_value = 90.0

        cut_percentage = max(0.0, min(100.0, 100.0 - win_percentage_value))
        Game.objects.filter(pk=game.pk).update(cut_percentage=cut_percentage)


def backwards(apps, schema_editor):
    Game = apps.get_model("games", "Game")

    for game in Game.objects.all().only("id", "cut_percentage"):
        cut_percentage = game.cut_percentage if game.cut_percentage is not None else 10
        try:
            cut_percentage_value = float(cut_percentage)
        except (TypeError, ValueError):
            cut_percentage_value = 10.0

        win_percentage = max(0.0, min(100.0, 100.0 - cut_percentage_value))
        Game.objects.filter(pk=game.pk).update(win_percentage=win_percentage)


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0007_game_cartella_statuses"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="cut_percentage",
            field=models.DecimalField(decimal_places=2, default=10, max_digits=5),
        ),
        migrations.RunPython(forwards, backwards),
    ]
