"""
Сервис для автоматического перевода новостей через LLM API.
Поддерживает OpenAI, Anthropic и DeepL.
"""
import logging
from typing import Dict, Optional
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class TranslationService:
    """
    Сервис для перевода текста через LLM API.
    """
    
    # Маппинг языков проекта на коды языков для API
    LANGUAGE_MAP = {
        'ru': 'Russian',
        'en': 'English',
        'de': 'German',
        'pt': 'Portuguese',
    }
    
    def __init__(self):
        self.provider = getattr(settings, 'TRANSLATION_PROVIDER', 'openai')
        self.api_key = getattr(settings, 'TRANSLATION_API_KEY', '')
        self.model = getattr(settings, 'TRANSLATION_MODEL', 'gpt-4o-mini')
        self.enabled = getattr(settings, 'TRANSLATION_ENABLED', True)
    
    def translate(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """
        Переводит текст с одного языка на другой.
        
        Args:
            text: Текст для перевода
            source_lang: Исходный язык (ru, en, de, pt)
            target_lang: Целевой язык (ru, en, de, pt)
        
        Returns:
            Переведенный текст или None в случае ошибки
        """
        if not self.enabled or not self.api_key:
            logger.warning("Translation is disabled or API key is not set")
            return None
        
        if source_lang == target_lang:
            return text
        
        if not text or not text.strip():
            return text
        
        try:
            if self.provider == 'openai':
                return self._translate_openai(text, source_lang, target_lang)
            elif self.provider == 'anthropic':
                return self._translate_anthropic(text, source_lang, target_lang)
            elif self.provider == 'deepl':
                return self._translate_deepl(text, source_lang, target_lang)
            else:
                logger.error(f"Unknown translation provider: {self.provider}")
                return None
        except Exception as e:
            logger.error(f"Translation error: {str(e)}")
            return None
    
    def _translate_openai(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """Перевод через OpenAI API"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.api_key)
            
            source_name = self.LANGUAGE_MAP.get(source_lang, source_lang)
            target_name = self.LANGUAGE_MAP.get(target_lang, target_lang)
            
            prompt = f"""Translate the following text from {source_name} to {target_name}. 
Preserve all HTML/Markdown formatting, links, and structure. 
Return only the translated text without any explanations or additional comments.

Text to translate:
{text}"""
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional translator. Translate accurately while preserving all formatting."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            translated_text = response.choices[0].message.content.strip()
            return translated_text
            
        except ImportError:
            logger.error("OpenAI library is not installed. Install it with: pip install openai")
            return None
        except Exception as e:
            logger.error(f"OpenAI translation error: {str(e)}")
            return None
    
    def _translate_anthropic(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """Перевод через Anthropic API (Claude)"""
        # TODO: Реализовать при необходимости
        logger.warning("Anthropic translation is not yet implemented")
        return None
    
    def _translate_deepl(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """Перевод через DeepL API"""
        # TODO: Реализовать при необходимости
        logger.warning("DeepL translation is not yet implemented")
        return None
    
    def translate_news(self, title: str, body: str, source_lang: str, target_languages: list = None) -> Dict[str, Dict[str, str]]:
        """
        Переводит заголовок и текст новости на все указанные языки.
        
        Args:
            title: Заголовок новости
            body: Текст новости
            source_lang: Исходный язык
            target_languages: Список целевых языков (по умолчанию все кроме исходного)
        
        Returns:
            Словарь вида {'ru': {'title': '...', 'body': '...'}, ...}
        """
        if target_languages is None:
            target_languages = [lang for lang in self.LANGUAGE_MAP.keys() if lang != source_lang]
        
        translations = {}
        
        for target_lang in target_languages:
            if target_lang == source_lang:
                translations[target_lang] = {
                    'title': title,
                    'body': body
                }
                continue
            
            translated_title = self.translate(title, source_lang, target_lang)
            translated_body = self.translate(body, source_lang, target_lang)
            
            if translated_title and translated_body:
                translations[target_lang] = {
                    'title': translated_title,
                    'body': translated_body
                }
            else:
                # Если перевод не удался, оставляем пустым (fallback сработает)
                logger.warning(f"Failed to translate to {target_lang}, leaving empty")
                translations[target_lang] = {
                    'title': '',
                    'body': ''
                }
        
        return translations

