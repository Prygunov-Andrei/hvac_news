from modeltranslation.translator import register, TranslationOptions
from .models import NewsPost

@register(NewsPost)
class NewsPostTranslationOptions(TranslationOptions):
    fields = ('title', 'body')

