from modeltranslation.translator import register, TranslationOptions
from .models import Manufacturer, Brand, NewsResource

@register(Manufacturer)
class ManufacturerTranslationOptions(TranslationOptions):
    fields = ('description',) # Имя обычно не переводится, но описание - да

@register(Brand)
class BrandTranslationOptions(TranslationOptions):
    fields = ('description',) # Имя бренда тоже обычно международное

@register(NewsResource)
class NewsResourceTranslationOptions(TranslationOptions):
    fields = ('description',)

