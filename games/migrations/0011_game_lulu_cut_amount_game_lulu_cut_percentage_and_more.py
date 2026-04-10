from django.db import migrations, models


def ensure_game_financial_columns(apps, schema_editor):
    table_name = "games_game"

    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    quoted_table = schema_editor.quote_name(table_name)

    if "lulu_cut_amount" not in columns:
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} "
            "ADD COLUMN lulu_cut_amount numeric(12,2) NOT NULL DEFAULT 0"
        )
    else:
        schema_editor.execute(
            f"UPDATE {quoted_table} SET lulu_cut_amount = 0 WHERE lulu_cut_amount IS NULL"
        )

    if "lulu_cut_percentage" not in columns:
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} "
            "ADD COLUMN lulu_cut_percentage numeric(5,2) NOT NULL DEFAULT 15"
        )
    else:
        schema_editor.execute(
            f"UPDATE {quoted_table} SET lulu_cut_percentage = 15 WHERE lulu_cut_percentage IS NULL"
        )

    if "shop_net_cut_amount" not in columns:
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} "
            "ADD COLUMN shop_net_cut_amount numeric(12,2) NOT NULL DEFAULT 0"
        )
    else:
        schema_editor.execute(
            f"UPDATE {quoted_table} SET shop_net_cut_amount = 0 WHERE shop_net_cut_amount IS NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0010_alter_shopbingosession_play_mode'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(ensure_game_financial_columns, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='game',
                    name='lulu_cut_amount',
                    field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                migrations.AddField(
                    model_name='game',
                    name='lulu_cut_percentage',
                    field=models.DecimalField(decimal_places=2, default=15, max_digits=5),
                ),
                migrations.AddField(
                    model_name='game',
                    name='shop_net_cut_amount',
                    field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
            ],
        ),
    ]
