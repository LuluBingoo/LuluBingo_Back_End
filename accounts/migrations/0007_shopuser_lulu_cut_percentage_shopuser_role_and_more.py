from django.db import migrations, models


def ensure_shopuser_financial_columns(apps, schema_editor):
    table_name = "accounts_shopuser"

    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    quoted_table = schema_editor.quote_name(table_name)

    if "role" not in columns:
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} "
            "ADD COLUMN role varchar(20) NOT NULL DEFAULT 'shop'"
        )
    else:
        schema_editor.execute(
            f"UPDATE {quoted_table} SET role = 'shop' WHERE role IS NULL"
        )

    if "shop_cut_percentage" not in columns:
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} "
            "ADD COLUMN shop_cut_percentage numeric(5,2) NOT NULL DEFAULT 10"
        )
    else:
        schema_editor.execute(
            f"UPDATE {quoted_table} SET shop_cut_percentage = 10 WHERE shop_cut_percentage IS NULL"
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


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_shopuser_two_factor_method_flags'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(ensure_shopuser_financial_columns, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='shopuser',
                    name='lulu_cut_percentage',
                    field=models.DecimalField(decimal_places=2, default=15, max_digits=5),
                ),
                migrations.AddField(
                    model_name='shopuser',
                    name='role',
                    field=models.CharField(choices=[('shop', 'Shop'), ('manager', 'Manager')], default='shop', max_length=20),
                ),
                migrations.AddField(
                    model_name='shopuser',
                    name='shop_cut_percentage',
                    field=models.DecimalField(decimal_places=2, default=10, max_digits=5),
                ),
            ],
        ),
    ]
