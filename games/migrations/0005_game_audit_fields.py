from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0004_game_call_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="awarded_claims",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="game",
            name="banned_cartellas",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="game",
            name="payout_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="game",
            name="shop_cut_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="game",
            name="total_pool",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="game",
            name="win_percentage",
            field=models.DecimalField(decimal_places=2, default=90, max_digits=5),
        ),
        migrations.AddField(
            model_name="game",
            name="winning_pattern",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
