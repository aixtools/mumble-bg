from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0000_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='mumbleuser',
            name='alliance_id',
            field=models.BigIntegerField(
                blank=True,
                help_text='Pilot alliance ID tracked in the FG/BG contract.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='mumbleuser',
            name='corporation_id',
            field=models.BigIntegerField(
                blank=True,
                help_text='Pilot corporation ID tracked in the FG/BG contract.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='mumbleuser',
            name='evepilot_id',
            field=models.BigIntegerField(
                blank=True,
                help_text='Pilot character ID tracked in the FG/BG contract.',
                null=True,
            ),
        ),
    ]
