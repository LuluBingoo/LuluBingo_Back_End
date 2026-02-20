from django.db import migrations, models
import django.utils.timezone
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0002_game_financial_timestamps"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="cartella_number_map",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="game",
            name="game_mode",
            field=models.CharField(
                choices=[("standard", "Standard"), ("shop_fixed4", "Shop Fixed 4")],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="game",
            name="min_bet_per_cartella",
            field=models.DecimalField(decimal_places=2, default=20, max_digits=12),
        ),
        migrations.AddField(
            model_name="game",
            name="shop_players_data",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="ShopBingoSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.CharField(editable=False, max_length=24, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("waiting", "Waiting"), ("locked", "Locked"), ("cancelled", "Cancelled")],
                        default="waiting",
                        max_length=20,
                    ),
                ),
                ("fixed_players", models.PositiveSmallIntegerField(default=4)),
                ("min_bet_per_cartella", models.DecimalField(decimal_places=2, default=20, max_digits=12)),
                ("players_data", models.JSONField(blank=True, default=list)),
                ("locked_cartellas", models.JSONField(blank=True, default=list)),
                ("total_payable", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "game",
                    models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shop_session", to="games.game"),
                ),
                (
                    "shop",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shop_bingo_sessions", to="accounts.shopuser"),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
