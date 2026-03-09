from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mumble', '0006_mumble_identity_sync'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mumbleuser',
            name='server',
            field=models.ForeignKey(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='accounts',
                to='mumble.mumbleserver',
            ),
            preserve_default=False,
        ),
    ]
