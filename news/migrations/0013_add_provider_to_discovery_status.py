# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0012_add_search_type_to_discovery_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='newsdiscoverystatus',
            name='provider',
            field=models.CharField(
                choices=[
                    ('auto', 'Автоматический выбор (цепочка)'),
                    ('grok', 'Grok 4.1 Fast'),
                    ('anthropic', 'Anthropic Claude Haiku 4.5'),
                    ('openai', 'OpenAI GPT-5.2'),
                ],
                default='auto',
                help_text='Провайдер LLM для поиска новостей',
                max_length=20,
                verbose_name='Provider'
            ),
        ),
    ]
