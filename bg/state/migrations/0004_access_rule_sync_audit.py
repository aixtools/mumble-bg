from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0003_rename_block_to_deny'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessRuleSyncAudit',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_id', models.CharField(blank=True, default='', max_length=64)),
                ('requested_by', models.CharField(blank=True, default='', max_length=255)),
                ('action', models.CharField(default='sync', max_length=16)),
                ('state_before', models.JSONField(default=dict, blank=True)),
                ('state_after', models.JSONField(default=dict, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
                'db_table': 'bg_access_rule_audit',
            },
        ),
    ]
