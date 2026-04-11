from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_shopuser_lulu_cut_percentage_shopuser_role_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shopuser",
            name="role",
            field=models.CharField(
                choices=[
                    ("shop", "Shop"),
                    ("manager", "Manager"),
                    ("developer", "Developer"),
                ],
                default="shop",
                max_length=20,
            ),
        ),
    ]
