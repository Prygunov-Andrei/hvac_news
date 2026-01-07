from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.files.storage import default_storage
from users.models import User
import os

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


class NewsDiscoveryRun(models.Model):
    """
    Модель для отслеживания последней даты поиска новостей.
    Хранит дату последнего успешного поиска для определения периода следующего поиска.
    """
    last_search_date = models.DateField(
        _("Last Search Date"),
        default=timezone.now,
        help_text=_("Дата последнего успешного поиска новостей")
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    
    class Meta:
        verbose_name = _("News Discovery Run")
        verbose_name_plural = _("News Discovery Runs")
        ordering = ['-last_search_date']
    
    def __str__(self):
        return f"Last search: {self.last_search_date}"
    
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
    def create_new_status(cls, total_count, search_type='resources'):
        """Создает новый статус для начала поиска"""
        # Закрываем все предыдущие running статусы для этого типа поиска
        cls.objects.filter(status='running', search_type=search_type).update(status='completed')
        return cls.objects.create(
            total_count=total_count,
            processed_count=0,
            status='running',
            search_type=search_type
        )
