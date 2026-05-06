# Generated migration for board_configuration field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0013_game_is_paused'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='board_configuration',
            field=models.JSONField(blank=True, default=dict, help_text='Shuffled board configuration for B, I, N, G, O columns'),
        ),
    ]
