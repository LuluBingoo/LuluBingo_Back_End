from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0005_game_audit_fields"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="game",
            index=models.Index(
                fields=["shop", "-created_at"],
                name="games_game_shop_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="game",
            index=models.Index(
                fields=["shop", "status", "-created_at"],
                name="g_game_shop_stat_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="game",
            index=models.Index(
                fields=["shop", "game_code"],
                name="games_game_shop_code_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="shopbingosession",
            index=models.Index(
                fields=["shop", "status", "-updated_at"],
                name="g_sess_shop_stat_updated_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="shopbingosession",
            index=models.Index(
                fields=["shop", "session_id"],
                name="games_session_shop_session_idx",
            ),
        ),
    ]
