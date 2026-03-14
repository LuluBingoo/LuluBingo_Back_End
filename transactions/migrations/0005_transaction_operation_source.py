from django.db import migrations, models


def ensure_operation_source_column(apps, schema_editor):
    table_name = "transactions_transaction"

    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    quoted_table = schema_editor.quote_name(table_name)

    if "operation_source" not in columns:
        schema_editor.execute(
            f"ALTER TABLE {quoted_table} "
            "ADD COLUMN operation_source varchar(30) NOT NULL DEFAULT 'system'"
        )
    else:
        schema_editor.execute(
            f"UPDATE {quoted_table} SET operation_source = 'system' "
            "WHERE operation_source IS NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0004_transaction_currency"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(ensure_operation_source_column, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="transaction",
                    name="operation_source",
                    field=models.CharField(
                        choices=[("api", "API"), ("admin", "Admin"), ("system", "System")],
                        default="system",
                        max_length=30,
                    ),
                ),
            ],
        ),
    ]
