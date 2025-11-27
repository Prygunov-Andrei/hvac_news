from django.db import models
from django.utils.translation import gettext_lazy as _

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
    name = models.CharField(_("Resource Name"), max_length=255)
    url = models.URLField(_("URL"))
    logo = models.ImageField(_("Logo"), upload_to='resources/logos/', blank=True, null=True)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        verbose_name = _("News Resource")
        verbose_name_plural = _("News Resources")
        ordering = ['name']

    def __str__(self):
        return self.name
