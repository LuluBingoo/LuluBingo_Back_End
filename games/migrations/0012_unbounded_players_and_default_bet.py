from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0011_game_lulu_cut_amount_game_lulu_cut_percentage_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="game",
            name="min_bet_per_cartella",
            field=models.DecimalField(decimal_places=2, default=10, max_digits=12),
        ),
        migrations.AlterField(
            model_name="shopbingosession",
            name="fixed_players",
            field=models.PositiveIntegerField(default=4),
        ),
        migrations.AlterField(
            model_name="shopbingosession",
            name="min_bet_per_cartella",
            field=models.DecimalField(decimal_places=2, default=10, max_digits=12),
        ),
    ]
