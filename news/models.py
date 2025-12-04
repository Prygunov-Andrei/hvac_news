from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from users.models import User

class NewsPost(models.Model):
    title = models.CharField(_("Title"), max_length=255)
    body = models.TextField(_("Body")) # Markdown content
    
    pub_date = models.DateTimeField(_("Publication Date"), default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Author"))
    
    # Для хранения оригинального архива (опционально, для истории)
    source_file = models.FileField(upload_to='news/archives/', blank=True, null=True)

    class Meta:
        verbose_name = _("News Post")
        verbose_name_plural = _("News Posts")
        ordering = ['-pub_date']

    def __str__(self):
        return self.title

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
