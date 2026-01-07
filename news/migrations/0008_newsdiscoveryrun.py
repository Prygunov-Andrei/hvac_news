# Generated manually

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0007_newspost_source_url'),
    ]

    operations = [
        migrations.CreateModel(
            name='NewsDiscoveryRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_search_date', models.DateField(default=django.utils.timezone.now, help_text='Дата последнего успешного поиска новостей', verbose_name='Last Search Date')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
            ],
            options={
                'verbose_name': 'News Discovery Run',
                'verbose_name_plural': 'News Discovery Runs',
                'ordering': ['-last_search_date'],
            },
        ),
    ]
