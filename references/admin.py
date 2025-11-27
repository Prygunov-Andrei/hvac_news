from django.contrib import admin
from modeltranslation.admin import TranslationAdmin
from .models import Manufacturer, Brand, NewsResource

@admin.register(Manufacturer)
class ManufacturerAdmin(TranslationAdmin):
    list_display = ('name', 'region')
    search_fields = ('name', 'region')

@admin.register(Brand)
class BrandAdmin(TranslationAdmin):
    list_display = ('name', 'manufacturer')
    search_fields = ('name', 'manufacturer__name')
    list_filter = ('manufacturer',)

@admin.register(NewsResource)
class NewsResourceAdmin(TranslationAdmin):
    list_display = ('name', 'url')
