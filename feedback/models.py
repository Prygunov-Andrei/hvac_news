from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class Feedback(models.Model):
    """
    Модель для обратной связи от пользователей.
    Любой пользователь (включая анонимных) может отправить сообщение.
    """
    email = models.EmailField(_("Email"), max_length=255)
    name = models.CharField(_("Name"), max_length=255, blank=True)
    message = models.TextField(_("Message"), max_length=2000)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    is_processed = models.BooleanField(_("Is Processed"), default=False, help_text=_("Mark as processed after admin review"))
    
    class Meta:
        verbose_name = _("Feedback")
        verbose_name_plural = _("Feedback Messages")
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback from {self.email} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"
