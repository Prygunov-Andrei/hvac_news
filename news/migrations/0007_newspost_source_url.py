# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0006_newspost_source_language'),
    ]

    operations = [
        migrations.AddField(
            model_name='newspost',
            name='source_url',
            field=models.URLField(blank=True, help_text='URL оригинального источника новости', null=True, verbose_name='Source URL'),
        ),
    ]
