from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class Manufacturer(models.Model):
    name = models.CharField(_("Name"), max_length=255)
    website_1 = models.URLField(_("Website 1"), blank=True, null=True)
    website_2 = models.URLField(_("Website 2"), blank=True, null=True)
    website_3 = models.URLField(_("Website 3"), blank=True, null=True)
    description = models.TextField(_("Description"), blank=True)
    region = models.CharField(_("Region"), max_length=100, blank=True) # Можно сделать Choices или отдельной моделью, пока строка

    class Meta:
        verbose_name = _("Manufacturer")
        verbose_name_plural = _("Manufacturers")
        ordering = ['name']

    def __str__(self):
        return self.name


class Brand(models.Model):
    manufacturer = models.ForeignKey(
        Manufacturer, 
        on_delete=models.CASCADE, 
        related_name='brands',
        verbose_name=_("Manufacturer")
    )
    name = models.CharField(_("Brand Name"), max_length=255)
    logo = models.ImageField(_("Logo"), upload_to='brands/logos/', blank=True, null=True)
    description = models.TextField(_("Description"), blank=True) # Уникальное описание для бренда

    class Meta:
        verbose_name = _("Brand")
        verbose_name_plural = _("Brands")
        ordering = ['name']

    def __str__(self):
        return self.name


class NewsResource(models.Model):
    # Типы источников
    SOURCE_TYPE_AUTO = 'auto'
    SOURCE_TYPE_MANUAL = 'manual'
    SOURCE_TYPE_HYBRID = 'hybrid'
    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_AUTO, _('Автоматический поиск')),
        (SOURCE_TYPE_MANUAL, _('Ручной ввод')),
        (SOURCE_TYPE_HYBRID, _('Гибридный (с кастомными инструкциями)')),
    ]
    
    name = models.CharField(_("Resource Name"), max_length=255)
    url = models.URLField(_("URL"))
    logo = models.ImageField(_("Logo"), upload_to='resources/logos/', blank=True, null=True)
    description = models.TextField(_("Description"), blank=True)
    section = models.CharField(_("Section"), max_length=255, blank=True, help_text=_("Section/region name from the resources file"))
    
    # Новые поля для классификации
    source_type = models.CharField(
        _("Source Type"),
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
        default=SOURCE_TYPE_AUTO,
        help_text=_("Тип источника: auto - автоматический поиск LLM, manual - только ручной ввод, hybrid - автопоиск с кастомными инструкциями")
    )
    language = models.CharField(
        _("Language"),
        max_length=10,
        choices=[
            ('ru', _('Russian (Русский)')),
            ('en', _('English (Английский)')),
            ('es', _('Spanish (Испанский)')),
            ('de', _('German (Немецкий)')),
            ('pt', _('Portuguese (Португальский)')),
            ('fr', _('French (Французский)')),
            ('it', _('Italian (Итальянский)')),
            ('tr', _('Turkish (Турецкий)')),
            ('ar', _('Arabic (Арабский)')),
            ('zh', _('Chinese (Китайский)')),
            ('ja', _('Japanese (Японский)')),
            ('ko', _('Korean (Корейский)')),
            ('pl', _('Polish (Польский)')),
            ('nl', _('Dutch (Голландский)')),
            ('sv', _('Swedish (Шведский)')),
            ('other', _('Other (Другой)')),
        ],
        default='en',
        help_text=_("Язык контента источника. Используется для генерации промпта на соответствующем языке.")
    )
    custom_search_instructions = models.TextField(
        _("Custom Search Instructions"),
        blank=True,
        help_text=_("Специальные инструкции для LLM по поиску новостей на этом источнике. "
                   "Используется для источников типа 'hybrid'. Если пусто - используется стандартный промпт.")
    )
    internal_notes = models.TextField(
        _("Internal Notes"),
        blank=True,
        help_text=_("Служебные заметки о источнике. Видны только администраторам. "
                   "Используйте для хранения служебной информации, замечаний, проблем и т.д.")
    )

    class Meta:
        verbose_name = _("News Resource")
        verbose_name_plural = _("News Resources")
        ordering = ['name']

    def __str__(self):
        return self.name
    
    @property
    def is_auto_searchable(self) -> bool:
        """Можно ли искать новости автоматически"""
        return self.source_type in [self.SOURCE_TYPE_AUTO, self.SOURCE_TYPE_HYBRID]
    
    @property
    def requires_manual_input(self) -> bool:
        """Требуется ли ручной ввод"""
        return self.source_type == self.SOURCE_TYPE_MANUAL


class NewsResourceStatistics(models.Model):
    """
    Статистика по источнику новостей для ранжирования и анализа.
    Обновляется автоматически при каждом поиске новостей.
    """
    resource = models.OneToOneField(
        NewsResource,
        on_delete=models.CASCADE,
        related_name='statistics',
        verbose_name=_("Resource")
    )
    
    # Общая статистика
    total_news_found = models.IntegerField(
        _("Total News Found"),
        default=0,
        help_text=_("Всего найдено новостей за все время")
    )
    total_searches = models.IntegerField(
        _("Total Searches"),
        default=0,
        help_text=_("Всего выполнено поисков")
    )
    total_no_news = models.IntegerField(
        _("Total No News"),
        default=0,
        help_text=_("Всего раз 'новостей не найдено'")
    )
    total_errors = models.IntegerField(
        _("Total Errors"),
        default=0,
        help_text=_("Всего ошибок при поиске")
    )
    
    # Временные метрики
    last_search_date = models.DateTimeField(
        _("Last Search Date"),
        null=True,
        blank=True,
        help_text=_("Дата и время последнего поиска")
    )
    last_news_date = models.DateTimeField(
        _("Last News Date"),
        null=True,
        blank=True,
        help_text=_("Дата и время последней найденной новости")
    )
    first_search_date = models.DateTimeField(
        _("First Search Date"),
        null=True,
        blank=True,
        help_text=_("Дата и время первого поиска")
    )
    
    # Процентные метрики
    success_rate = models.FloatField(
        _("Success Rate"),
        default=0.0,
        help_text=_("Процент успешных поисков (найдено новостей) в процентах")
    )
    error_rate = models.FloatField(
        _("Error Rate"),
        default=0.0,
        help_text=_("Процент ошибок в процентах")
    )
    
    # Средние значения
    avg_news_per_search = models.FloatField(
        _("Average News Per Search"),
        default=0.0,
        help_text=_("Среднее количество новостей за один поиск")
    )
    
    # Периодическая статистика
    news_last_30_days = models.IntegerField(
        _("News Last 30 Days"),
        default=0,
        help_text=_("Количество новостей за последние 30 дней")
    )
    news_last_90_days = models.IntegerField(
        _("News Last 90 Days"),
        default=0,
        help_text=_("Количество новостей за последние 90 дней")
    )
    searches_last_30_days = models.IntegerField(
        _("Searches Last 30 Days"),
        default=0,
        help_text=_("Количество поисков за последние 30 дней")
    )
    
    # Рейтинг и приоритет
    ranking_score = models.FloatField(
        _("Ranking Score"),
        default=0.0,
        help_text=_("Общий рейтинг для сортировки (чем выше, тем лучше)")
    )
    priority = models.IntegerField(
        _("Priority"),
        default=0,
        help_text=_("Приоритет обработки (чем выше, тем раньше обрабатывать)")
    )
    
    # Флаги статуса
    is_active = models.BooleanField(
        _("Is Active"),
        default=True,
        help_text=_("Активен ли источник (есть новости за последние 90 дней)")
    )
    
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    
    class Meta:
        verbose_name = _("News Resource Statistics")
        verbose_name_plural = _("News Resources Statistics")
        ordering = ['-ranking_score', '-total_news_found']
        indexes = [
            models.Index(fields=['-ranking_score']),
            models.Index(fields=['is_active', '-ranking_score']),
            models.Index(fields=['-total_news_found']),
        ]
    
    def __str__(self):
        return f"Statistics for {self.resource.name}"
    
    def calculate_ranking_score(self):
        """
        Вычисляет составной рейтинг источника.
        Формула:
        - Общая продуктивность (30%)
        - Текущая активность за 30 дней (30%)
        - Процент успешных поисков (20%)
        - Среднее количество новостей за поиск (20%)
        """
        # Нормализуем значения для расчета (чтобы все были в диапазоне 0-100)
        total_news_score = min(self.total_news_found / 10, 100)  # Максимум 1000 новостей = 100 баллов
        activity_score = min(self.news_last_30_days * 5, 100)  # Максимум 20 новостей за 30 дней = 100 баллов
        success_score = self.success_rate  # Уже в процентах 0-100
        avg_news_score = min(self.avg_news_per_search * 20, 100)  # Максимум 5 новостей за поиск = 100 баллов
        
        # Взвешенная сумма
        score = (
            total_news_score * 0.3 +
            activity_score * 0.3 +
            success_score * 0.2 +
            avg_news_score * 0.2
        )
        
        return round(score, 2)
    
    def update_active_status(self):
        """Обновляет флаг активности на основе последних 90 дней"""
        self.is_active = self.news_last_90_days > 0


class ManufacturerStatistics(models.Model):
    """
    Статистика по производителю для ранжирования и анализа.
    Обновляется автоматически при каждом поиске новостей о производителе.
    """
    manufacturer = models.OneToOneField(
        Manufacturer,
        on_delete=models.CASCADE,
        related_name='statistics',
        verbose_name=_("Manufacturer")
    )
    
    # Общая статистика
    total_news_found = models.IntegerField(
        _("Total News Found"),
        default=0,
        help_text=_("Всего найдено новостей за все время")
    )
    total_searches = models.IntegerField(
        _("Total Searches"),
        default=0,
        help_text=_("Всего выполнено поисков")
    )
    total_no_news = models.IntegerField(
        _("Total No News"),
        default=0,
        help_text=_("Всего раз 'новостей не найдено'")
    )
    total_errors = models.IntegerField(
        _("Total Errors"),
        default=0,
        help_text=_("Всего ошибок при поиске")
    )
    
    # Временные метрики
    last_search_date = models.DateTimeField(
        _("Last Search Date"),
        null=True,
        blank=True,
        help_text=_("Дата и время последнего поиска")
    )
    last_news_date = models.DateTimeField(
        _("Last News Date"),
        null=True,
        blank=True,
        help_text=_("Дата и время последней найденной новости")
    )
    first_search_date = models.DateTimeField(
        _("First Search Date"),
        null=True,
        blank=True,
        help_text=_("Дата и время первого поиска")
    )
    
    # Процентные метрики
    success_rate = models.FloatField(
        _("Success Rate"),
        default=0.0,
        help_text=_("Процент успешных поисков (найдено новостей) в процентах")
    )
    error_rate = models.FloatField(
        _("Error Rate"),
        default=0.0,
        help_text=_("Процент ошибок в процентах")
    )
    
    # Средние значения
    avg_news_per_search = models.FloatField(
        _("Average News Per Search"),
        default=0.0,
        help_text=_("Среднее количество новостей за один поиск")
    )
    
    # Периодическая статистика
    news_last_30_days = models.IntegerField(
        _("News Last 30 Days"),
        default=0,
        help_text=_("Количество новостей за последние 30 дней")
    )
    news_last_90_days = models.IntegerField(
        _("News Last 90 Days"),
        default=0,
        help_text=_("Количество новостей за последние 90 дней")
    )
    searches_last_30_days = models.IntegerField(
        _("Searches Last 30 Days"),
        default=0,
        help_text=_("Количество поисков за последние 30 дней")
    )
    
    # Рейтинг и приоритет
    ranking_score = models.FloatField(
        _("Ranking Score"),
        default=0.0,
        help_text=_("Общий рейтинг для сортировки (чем выше, тем лучше)")
    )
    priority = models.IntegerField(
        _("Priority"),
        default=0,
        help_text=_("Приоритет обработки (чем выше, тем раньше обрабатывать)")
    )
    
    # Флаги статуса
    is_active = models.BooleanField(
        _("Is Active"),
        default=True,
        help_text=_("Активен ли производитель (есть новости за последние 90 дней)")
    )
    
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    
    class Meta:
        verbose_name = _("Manufacturer Statistics")
        verbose_name_plural = _("Manufacturers Statistics")
        ordering = ['-ranking_score', '-total_news_found']
        indexes = [
            models.Index(fields=['-ranking_score']),
            models.Index(fields=['is_active', '-ranking_score']),
            models.Index(fields=['-total_news_found']),
        ]
    
    def __str__(self):
        return f"Statistics for {self.manufacturer.name}"
    
    def calculate_ranking_score(self):
        """
        Вычисляет составной рейтинг производителя.
        Формула:
        - Общая продуктивность (30%)
        - Текущая активность за 30 дней (30%)
        - Процент успешных поисков (20%)
        - Среднее количество новостей за поиск (20%)
        """
        # Нормализуем значения для расчета (чтобы все были в диапазоне 0-100)
        total_news_score = min(self.total_news_found / 10, 100)  # Максимум 1000 новостей = 100 баллов
        activity_score = min(self.news_last_30_days * 5, 100)  # Максимум 20 новостей за 30 дней = 100 баллов
        success_score = self.success_rate  # Уже в процентах 0-100
        avg_news_score = min(self.avg_news_per_search * 20, 100)  # Максимум 5 новостей за поиск = 100 баллов
        
        # Взвешенная сумма
        score = (
            total_news_score * 0.3 +
            activity_score * 0.3 +
            success_score * 0.2 +
            avg_news_score * 0.2
        )
        
        return round(score, 2)
    
    def update_active_status(self):
        """Обновляет флаг активности на основе последних 90 дней"""
        self.is_active = self.news_last_90_days > 0
