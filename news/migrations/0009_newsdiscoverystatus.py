# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0008_newsdiscoveryrun'),
    ]

    operations = [
        migrations.CreateModel(
            name='NewsDiscoveryStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('processed_count', models.IntegerField(default=0, help_text='Количество обработанных источников', verbose_name='Processed Count')),
                ('total_count', models.IntegerField(default=0, help_text='Общее количество источников для обработки', verbose_name='Total Count')),
                ('status', models.CharField(choices=[('running', 'Running'), ('completed', 'Completed'), ('error', 'Error')], default='running', help_text='Статус процесса поиска', max_length=20, verbose_name='Status')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
            ],
            options={
                'verbose_name': 'News Discovery Status',
                'verbose_name_plural': 'News Discovery Statuses',
                'ordering': ['-created_at'],
            },
        ),
    ]
