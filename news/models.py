from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.files.storage import default_storage
from users.models import User
import os


def get_today_date():
    """Возвращает сегодняшнюю дату (без времени) для использования как default в DateField"""
    return timezone.now().date()

class NewsPost(models.Model):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('scheduled', _('Scheduled')),
        ('published', _('Published')),
    ]
    
    title = models.CharField(_("Title"), max_length=255)
    body = models.TextField(_("Body")) # Markdown content
    source_url = models.URLField(_("Source URL"), blank=True, null=True, help_text=_("URL оригинального источника новости"))
    
    # Связь с производителем (если новость найдена по производителю)
    manufacturer = models.ForeignKey(
        'references.Manufacturer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='news_posts',
        verbose_name=_("Manufacturer"),
        help_text=_("Производитель, по которому была найдена новость")
    )
    
    pub_date = models.DateTimeField(_("Publication Date"), default=timezone.now)
    status = models.CharField(
        _("Status"), 
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='draft',
        help_text=_("Draft: не опубликовано, Scheduled: запланировано, Published: опубликовано")
    )
    source_language = models.CharField(
        _("Source Language"),
        max_length=10,
        default='ru',
        help_text=_("Исходный язык новости (ru, en, de, pt)")
    )
    is_no_news_found = models.BooleanField(
        _("No News Found"),
        default=False,
        help_text=_("Пометка для записей 'новостей не найдено'. Используется для фильтрации и массового удаления на фронтенде.")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Author"))
    
    # Для хранения оригинального архива (опционально, для истории)
    source_file = models.FileField(upload_to='news/archives/', blank=True, null=True)

    class Meta:
        verbose_name = _("News Post")
        verbose_name_plural = _("News Posts")
        ordering = ['-pub_date']
        indexes = [
            models.Index(fields=['status', '-pub_date']),
        ]

    def __str__(self):
        return self.title
    
    def is_published(self):
        """Проверяет, опубликована ли новость"""
        return (
            self.status == 'published' and 
            self.pub_date <= timezone.now()
        )

class NewsMedia(models.Model):
    """
    Модель для хранения медиа-файлов, привязанных к новости.
    Это позволяет нам удалять файлы при удалении новости.
    """
    news_post = models.ForeignKey(NewsPost, on_delete=models.CASCADE, related_name='media')
    file = models.FileField(upload_to='news/media/')
    media_type = models.CharField(max_length=20, choices=[('image', 'Image'), ('video', 'Video')])
    original_name = models.CharField(max_length=255, help_text="Original filename in the zip")

    def __str__(self):
        return f"{self.media_type}: {self.original_name}"


class Comment(models.Model):
    """
    Модель комментария к новости.
    Пользователи могут создавать, редактировать и удалять свои комментарии.
    """
    news_post = models.ForeignKey(NewsPost, on_delete=models.CASCADE, related_name='comments', verbose_name=_("News Post"))
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments', verbose_name=_("Author"))
    text = models.TextField(_("Text"), max_length=2000)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("Comment")
        verbose_name_plural = _("Comments")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['news_post', '-created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.author.email} on {self.news_post.title[:50]}"


def media_upload_path(instance, filename):
    """Генерирует путь для загрузки медиафайлов: news/uploads/YYYY/MM/filename"""
    year = timezone.now().strftime('%Y')
    month = timezone.now().strftime('%m')
    return f'news/uploads/{year}/{month}/{filename}'


class MediaUpload(models.Model):
    """
    Модель для загрузки медиафайлов через веб-интерфейс.
    Используется для временного хранения файлов перед вставкой в новость.
    """
    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]
    
    file = models.FileField(_("File"), upload_to=media_upload_path)
    media_type = models.CharField(_("Media Type"), max_length=20, choices=MEDIA_TYPE_CHOICES, blank=True)
    uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='uploaded_media',
        verbose_name=_("Uploaded By")
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    
    class Meta:
        verbose_name = _("Media Upload")
        verbose_name_plural = _("Media Uploads")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.media_type}: {os.path.basename(self.file.name)}"
    
    def delete(self, *args, **kwargs):
        """Удаляет файл при удалении записи"""
        if self.file:
            if default_storage.exists(self.file.name):
                default_storage.delete(self.file.name)
        super().delete(*args, **kwargs)


class SearchConfiguration(models.Model):
    """
    Конфигурация параметров поиска новостей.
    Позволяет настраивать все параметры LLM без изменения кода.
    """
    PROVIDER_CHOICES = [
        ('grok', 'Grok (xAI)'),
        ('anthropic', 'Anthropic Claude'),
        ('gemini', 'Google Gemini'),
        ('openai', 'OpenAI GPT'),
    ]
    
    SEARCH_CONTEXT_CHOICES = [
        ('low', 'Low (минимальный контекст, дешевле)'),
        ('medium', 'Medium (баланс)'),
        ('high', 'High (максимальный контекст, дороже)'),
    ]
    
    name = models.CharField(
        _("Configuration Name"),
        max_length=100,
        default="default",
        help_text=_("Название конфигурации для идентификации")
    )
    is_active = models.BooleanField(
        _("Is Active"),
        default=False,
        help_text=_("Только одна конфигурация может быть активной")
    )
    
    # Основной провайдер и цепочка fallback
    primary_provider = models.CharField(
        _("Primary Provider"),
        max_length=20,
        choices=PROVIDER_CHOICES,
        default='grok',
        help_text=_("Основной провайдер для поиска")
    )
    fallback_chain = models.JSONField(
        _("Fallback Chain"),
        default=list,
        blank=True,
        help_text=_("Цепочка резервных провайдеров: ['anthropic', 'gemini', 'openai']")
    )
    
    # LLM параметры
    temperature = models.FloatField(
        _("Temperature"),
        default=0.3,
        help_text=_("Температура LLM (0.0-1.0). Меньше = более детерминированный")
    )
    timeout = models.IntegerField(
        _("Timeout (seconds)"),
        default=120,
        help_text=_("Таймаут запроса к LLM в секундах")
    )
    
    # Grok web search параметры
    max_search_results = models.IntegerField(
        _("Max Search Results"),
        default=5,
        help_text=_("Макс. количество результатов веб-поиска Grok (влияет на стоимость!)")
    )
    search_context_size = models.CharField(
        _("Search Context Size"),
        max_length=10,
        choices=SEARCH_CONTEXT_CHOICES,
        default='low',
        help_text=_("Размер контекста для веб-поиска")
    )
    
    # Модели LLM
    grok_model = models.CharField(
        _("Grok Model"),
        max_length=50,
        default='grok-4-1-fast',
        help_text=_("Модель Grok (xAI)")
    )
    anthropic_model = models.CharField(
        _("Anthropic Model"),
        max_length=50,
        default='claude-3-5-haiku-20241022',
        help_text=_("Модель Anthropic Claude")
    )
    gemini_model = models.CharField(
        _("Gemini Model"),
        max_length=50,
        default='gemini-2.0-flash-exp',
        help_text=_("Модель Google Gemini")
    )
    openai_model = models.CharField(
        _("OpenAI Model"),
        max_length=50,
        default='gpt-4o',
        help_text=_("Модель OpenAI GPT")
    )
    
    # Лимиты
    max_news_per_resource = models.IntegerField(
        _("Max News Per Resource"),
        default=10,
        help_text=_("Максимум новостей с одного источника за один поиск")
    )
    delay_between_requests = models.FloatField(
        _("Delay Between Requests (seconds)"),
        default=0.5,
        help_text=_("Задержка между запросами к API в секундах")
    )
    
    # Тарифы для расчёта стоимости (цена за 1М токенов в USD)
    grok_input_price = models.DecimalField(
        _("Grok Input Price (per 1M tokens)"),
        max_digits=10,
        decimal_places=4,
        default=3.0,
        help_text=_("Цена за 1М входных токенов Grok в USD")
    )
    grok_output_price = models.DecimalField(
        _("Grok Output Price (per 1M tokens)"),
        max_digits=10,
        decimal_places=4,
        default=15.0,
        help_text=_("Цена за 1М выходных токенов Grok в USD")
    )
    anthropic_input_price = models.DecimalField(
        _("Anthropic Input Price (per 1M tokens)"),
        max_digits=10,
        decimal_places=4,
        default=0.80,
        help_text=_("Цена за 1М входных токенов Anthropic в USD")
    )
    anthropic_output_price = models.DecimalField(
        _("Anthropic Output Price (per 1M tokens)"),
        max_digits=10,
        decimal_places=4,
        default=4.0,
        help_text=_("Цена за 1М выходных токенов Anthropic в USD")
    )
    gemini_input_price = models.DecimalField(
        _("Gemini Input Price (per 1M tokens)"),
        max_digits=10,
        decimal_places=4,
        default=0.075,
        help_text=_("Цена за 1М входных токенов Gemini в USD")
    )
    gemini_output_price = models.DecimalField(
        _("Gemini Output Price (per 1M tokens)"),
        max_digits=10,
        decimal_places=4,
        default=0.30,
        help_text=_("Цена за 1М выходных токенов Gemini в USD")
    )
    openai_input_price = models.DecimalField(
        _("OpenAI Input Price (per 1M tokens)"),
        max_digits=10,
        decimal_places=4,
        default=2.50,
        help_text=_("Цена за 1М входных токенов OpenAI в USD")
    )
    openai_output_price = models.DecimalField(
        _("OpenAI Output Price (per 1M tokens)"),
        max_digits=10,
        decimal_places=4,
        default=10.0,
        help_text=_("Цена за 1М выходных токенов OpenAI в USD")
    )
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("Search Configuration")
        verbose_name_plural = _("Search Configurations")
        ordering = ['-is_active', '-updated_at']
    
    def __str__(self):
        active = " ✓" if self.is_active else ""
        return f"{self.name}{active}"
    
    def save(self, *args, **kwargs):
        """При активации конфигурации деактивируем остальные"""
        if self.is_active:
            SearchConfiguration.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active(cls):
        """Возвращает активную конфигурацию или создаёт дефолтную"""
        config = cls.objects.filter(is_active=True).first()
        if not config:
            config = cls.objects.first()
            if config:
                config.is_active = True
                config.save()
            else:
                config = cls.objects.create(name="default", is_active=True)
        return config
    
    def get_price(self, provider: str, token_type: str) -> float:
        """Возвращает цену за 1М токенов для провайдера"""
        field_name = f"{provider}_{token_type}_price"
        return float(getattr(self, field_name, 0))
    
    def to_dict(self) -> dict:
        """Возвращает снимок конфигурации как словарь"""
        return {
            'name': self.name,
            'primary_provider': self.primary_provider,
            'fallback_chain': self.fallback_chain,
            'temperature': self.temperature,
            'timeout': self.timeout,
            'max_search_results': self.max_search_results,
            'search_context_size': self.search_context_size,
            'grok_model': self.grok_model,
            'anthropic_model': self.anthropic_model,
            'gemini_model': self.gemini_model,
            'openai_model': self.openai_model,
            'max_news_per_resource': self.max_news_per_resource,
            'delay_between_requests': self.delay_between_requests,
            'prices': {
                'grok': {'input': float(self.grok_input_price), 'output': float(self.grok_output_price)},
                'anthropic': {'input': float(self.anthropic_input_price), 'output': float(self.anthropic_output_price)},
                'gemini': {'input': float(self.gemini_input_price), 'output': float(self.gemini_output_price)},
                'openai': {'input': float(self.openai_input_price), 'output': float(self.openai_output_price)},
            }
        }


class NewsDiscoveryRun(models.Model):
    """
    Модель для отслеживания запусков поиска новостей.
    Хранит историю с полными метриками и снимком конфигурации.
    """
    last_search_date = models.DateField(
        _("Last Search Date"),
        default=get_today_date,
        help_text=_("Дата последнего успешного поиска новостей")
    )
    
    # Снимок конфигурации на момент запуска
    config_snapshot = models.JSONField(
        _("Config Snapshot"),
        null=True,
        blank=True,
        help_text=_("Копия конфигурации на момент запуска поиска")
    )
    
    # Временные метрики
    started_at = models.DateTimeField(
        _("Started At"),
        null=True,
        blank=True,
        help_text=_("Время начала поиска")
    )
    finished_at = models.DateTimeField(
        _("Finished At"),
        null=True,
        blank=True,
        help_text=_("Время завершения поиска")
    )
    
    # Метрики API
    total_requests = models.IntegerField(
        _("Total Requests"),
        default=0,
        help_text=_("Общее количество запросов к API")
    )
    total_input_tokens = models.IntegerField(
        _("Total Input Tokens"),
        default=0,
        help_text=_("Общее количество входных токенов")
    )
    total_output_tokens = models.IntegerField(
        _("Total Output Tokens"),
        default=0,
        help_text=_("Общее количество выходных токенов")
    )
    estimated_cost_usd = models.DecimalField(
        _("Estimated Cost (USD)"),
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text=_("Расчётная стоимость в USD")
    )
    
    # Метрики по провайдерам
    provider_stats = models.JSONField(
        _("Provider Stats"),
        default=dict,
        blank=True,
        help_text=_("Статистика по провайдерам: {provider: {requests, input_tokens, output_tokens, cost, errors}}")
    )
    
    # Результаты
    news_found = models.IntegerField(
        _("News Found"),
        default=0,
        help_text=_("Количество найденных новостей")
    )
    news_duplicates = models.IntegerField(
        _("News Duplicates"),
        default=0,
        help_text=_("Количество дубликатов (пропущенных)")
    )
    resources_processed = models.IntegerField(
        _("Resources Processed"),
        default=0,
        help_text=_("Количество обработанных ресурсов")
    )
    resources_failed = models.IntegerField(
        _("Resources Failed"),
        default=0,
        help_text=_("Количество ресурсов с ошибками")
    )
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("News Discovery Run")
        verbose_name_plural = _("News Discovery Runs")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        cost = f"${self.estimated_cost_usd:.2f}" if self.estimated_cost_usd else "$0"
        return f"Run {self.created_at.strftime('%Y-%m-%d %H:%M')} - {self.news_found} news, {cost}"
    
    def get_duration_seconds(self) -> int:
        """Возвращает длительность поиска в секундах"""
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds())
        return 0
    
    def get_duration_display(self) -> str:
        """Возвращает длительность в формате HH:MM:SS"""
        seconds = self.get_duration_seconds()
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def get_efficiency(self) -> float:
        """Возвращает эффективность: новости / доллар"""
        if self.estimated_cost_usd and self.estimated_cost_usd > 0:
            return float(self.news_found / float(self.estimated_cost_usd))
        return 0
    
    @classmethod
    def get_last_search_date(cls):
        """Возвращает дату последнего поиска или сегодняшнюю дату, если поисков еще не было"""
        last_run = cls.objects.first()
        if last_run:
            return last_run.last_search_date
        return timezone.now().date()
    
    @classmethod
    def update_last_search_date(cls, date=None):
        """Обновляет дату последнего поиска"""
        if date is None:
            date = timezone.now().date()
        
        last_run = cls.objects.first()
        if last_run:
            last_run.last_search_date = date
            last_run.save()
        else:
            cls.objects.create(last_search_date=date)
    
    @classmethod
    def start_new_run(cls, config: 'SearchConfiguration' = None):
        """Создаёт новый запуск поиска с конфигурацией"""
        if config is None:
            config = SearchConfiguration.get_active()
        
        return cls.objects.create(
            last_search_date=timezone.now().date(),
            config_snapshot=config.to_dict() if config else None,
            started_at=timezone.now(),
            provider_stats={}
        )
    
    def finish(self):
        """Завершает запуск поиска"""
        self.finished_at = timezone.now()
        self.save()
    
    def add_api_call(self, provider: str, input_tokens: int, output_tokens: int, 
                     cost: float, success: bool = True):
        """Добавляет статистику вызова API"""
        if provider not in self.provider_stats:
            self.provider_stats[provider] = {
                'requests': 0,
                'input_tokens': 0,
                'output_tokens': 0,
                'cost': 0,
                'errors': 0
            }
        
        stats = self.provider_stats[provider]
        stats['requests'] += 1
        stats['input_tokens'] += input_tokens
        stats['output_tokens'] += output_tokens
        stats['cost'] += cost
        if not success:
            stats['errors'] += 1
        
        self.total_requests += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.estimated_cost_usd = float(self.estimated_cost_usd) + cost
        self.save()


class DiscoveryAPICall(models.Model):
    """
    Детальная запись каждого вызова API при поиске новостей.
    Позволяет анализировать эффективность по источникам и провайдерам.
    """
    discovery_run = models.ForeignKey(
        NewsDiscoveryRun,
        on_delete=models.CASCADE,
        related_name='api_calls',
        verbose_name=_("Discovery Run")
    )
    resource = models.ForeignKey(
        'references.NewsResource',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discovery_calls',
        verbose_name=_("Resource")
    )
    manufacturer = models.ForeignKey(
        'references.Manufacturer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discovery_calls',
        verbose_name=_("Manufacturer")
    )
    
    provider = models.CharField(
        _("Provider"),
        max_length=20,
        help_text=_("Провайдер LLM")
    )
    model = models.CharField(
        _("Model"),
        max_length=50,
        help_text=_("Использованная модель")
    )
    
    input_tokens = models.IntegerField(
        _("Input Tokens"),
        default=0
    )
    output_tokens = models.IntegerField(
        _("Output Tokens"),
        default=0
    )
    cost_usd = models.DecimalField(
        _("Cost (USD)"),
        max_digits=10,
        decimal_places=6,
        default=0
    )
    
    duration_ms = models.IntegerField(
        _("Duration (ms)"),
        default=0,
        help_text=_("Время выполнения запроса в миллисекундах")
    )
    success = models.BooleanField(
        _("Success"),
        default=True
    )
    error_message = models.TextField(
        _("Error Message"),
        blank=True,
        default=''
    )
    
    news_extracted = models.IntegerField(
        _("News Extracted"),
        default=0,
        help_text=_("Количество новостей, извлечённых из этого запроса")
    )
    
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    
    class Meta:
        verbose_name = _("Discovery API Call")
        verbose_name_plural = _("Discovery API Calls")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['discovery_run', '-created_at']),
            models.Index(fields=['provider', '-created_at']),
        ]
    
    def __str__(self):
        target = self.resource.name if self.resource else (self.manufacturer.name if self.manufacturer else "Unknown")
        return f"{self.provider}: {target} - {self.news_extracted} news"


class NewsDiscoveryStatus(models.Model):
    """
    Модель для отслеживания текущего статуса поиска новостей.
    Используется для индикатора прогресса в админ-интерфейсе.
    """
    STATUS_CHOICES = [
        ('running', _('Running')),
        ('completed', _('Completed')),
        ('error', _('Error')),
    ]
    
    SEARCH_TYPE_CHOICES = [
        ('resources', _('Resources')),
        ('manufacturers', _('Manufacturers')),
    ]
    
    search_type = models.CharField(
        _("Search Type"),
        max_length=20,
        choices=SEARCH_TYPE_CHOICES,
        default='resources',
        help_text=_("Тип поиска: источники или производители")
    )
    
    processed_count = models.IntegerField(
        _("Processed Count"),
        default=0,
        help_text=_("Количество обработанных источников/производителей")
    )
    total_count = models.IntegerField(
        _("Total Count"),
        default=0,
        help_text=_("Общее количество источников/производителей для обработки")
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='running',
        help_text=_("Статус процесса поиска")
    )
    provider = models.CharField(
        _("Provider"),
        max_length=20,
        choices=[
            ('auto', _('Автоматический выбор (цепочка)')),
            ('grok', _('Grok 4.1 Fast')),
            ('anthropic', _('Anthropic Claude Haiku 4.5')),
            ('openai', _('OpenAI GPT-5.2')),
        ],
        default='auto',
        help_text=_("Провайдер LLM для поиска новостей")
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("News Discovery Status")
        verbose_name_plural = _("News Discovery Statuses")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['search_type', 'status']),
        ]
    
    def __str__(self):
        return f"Status: {self.status} ({self.processed_count}/{self.total_count})"
    
    def get_progress_percent(self):
        """Возвращает процент выполнения (0-100)"""
        if self.total_count == 0:
            return 0
        return int((self.processed_count / self.total_count) * 100)
    
    @classmethod
    def get_current_status(cls, search_type='resources'):
        """Возвращает текущий статус для указанного типа поиска или None"""
        return cls.objects.filter(status='running', search_type=search_type).first()
    
    @classmethod
    def create_new_status(cls, total_count, search_type='resources', provider='auto'):
        """Создает новый статус для начала поиска"""
        # Закрываем все предыдущие running статусы для этого типа поиска
        cls.objects.filter(status='running', search_type=search_type).update(status='completed')
        return cls.objects.create(
            total_count=total_count,
            search_type=search_type,
            provider=provider,
            processed_count=0,
            status='running'
        )
