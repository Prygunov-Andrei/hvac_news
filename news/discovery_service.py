"""
Сервис для автоматического поиска новостей через LLM API.
Использует Grok 4.1 Fast (xAI) с встроенным веб-поиском как основной провайдер.
OpenAI GPT-5.2 с Responses API используется как резервный вариант.
"""
import logging
import json
from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from references.models import NewsResource, NewsResourceStatistics, Manufacturer, ManufacturerStatistics
from .models import NewsPost, NewsDiscoveryRun, NewsDiscoveryStatus
from users.models import User

logger = logging.getLogger(__name__)


class NewsDiscoveryService:
    """
    Сервис для автоматического поиска новостей через LLM API.
    """
    
    SUPPORTED_LANGUAGES = ['ru', 'en', 'de', 'pt']
    
    def __init__(self, user: Optional[User] = None):
        self.user = user
        self.openai_api_key = getattr(settings, 'TRANSLATION_API_KEY', '')
        self.openai_model = getattr(settings, 'NEWS_DISCOVERY_OPENAI_MODEL', 'gpt-5.2')
        self.grok_api_key = getattr(settings, 'XAI_API_KEY', '')
        self.grok_model = getattr(settings, 'NEWS_DISCOVERY_GROK_MODEL', 'grok-4-1-fast')
        self.use_grok = getattr(settings, 'NEWS_DISCOVERY_USE_GROK', True)
        self.use_openai_fallback = getattr(settings, 'NEWS_DISCOVERY_USE_OPENAI_FALLBACK', True)
        self.timeout = int(getattr(settings, 'NEWS_DISCOVERY_TIMEOUT', '120'))  # Таймаут в секундах
        # Grok используется как основной провайдер, OpenAI как резервный
    
    def discover_news_for_resource(self, resource: NewsResource) -> Tuple[int, int, Optional[str]]:
        """
        Ищет новости для одного источника.
        
        Args:
            resource: Источник новостей
            
        Returns:
            Tuple[created_count, error_count, error_message]
        """
        # Получаем период поиска
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        
        # Формируем промпт для LLM
        prompt = self._build_search_prompt(resource, last_search_date, today)
        
        # Получаем ответ от LLM (Grok как основной, OpenAI как резервный)
        llm_response = None
        llm_error = None
        provider_used = None
        
        # Пробуем сначала Grok, если включен
        if self.use_grok and self.grok_api_key:
            try:
                logger.info(f"[Grok] Начинаю обработку ресурса {resource.id} ({resource.name})")
                llm_response = self._query_grok(prompt)
                provider_used = 'Grok'
                logger.info(f"[Grok] ✅ Успешно обработал ресурс {resource.id} ({resource.name})")
            except Exception as e:
                logger.warning(f"[Grok] ❌ Ошибка для ресурса {resource.id}: {str(e)}")
                llm_error = f"Grok: {str(e)}"
                # Если есть fallback на OpenAI - пробуем его
                if self.use_openai_fallback and self.openai_api_key:
                    try:
                        logger.info(f"[OpenAI Fallback] Пробую обработать ресурс {resource.id} ({resource.name})")
                        llm_response = self._query_openai(prompt)
                        provider_used = 'OpenAI (fallback)'
                        logger.info(f"[OpenAI Fallback] ✅ Успешно обработал ресурс {resource.id} ({resource.name})")
                    except Exception as e2:
                        logger.error(f"[OpenAI Fallback] ❌ Ошибка для ресурса {resource.id}: {str(e2)}")
                        llm_error = f"{llm_error}; OpenAI fallback: {str(e2)}"
                        self._create_error_news(resource, f"Ошибка обоих провайдеров: {llm_error}")
                        # Обновляем статистику при ошибке
                        self._update_resource_statistics(
                            resource=resource,
                            news_count=0,
                            error_count=1,
                            is_no_news=False,
                            has_errors=True
                        )
                        return 0, 1, f"Ошибка обоих провайдеров: {llm_error}"
        # Если Grok не используется или нет ключа - используем OpenAI
        elif self.openai_api_key:
            try:
                llm_response = self._query_openai(prompt)
                provider_used = 'OpenAI'
                logger.info(f"OpenAI успешно обработал ресурс {resource.id}")
            except Exception as e:
                logger.error(f"OpenAI error for resource {resource.id}: {str(e)}")
                llm_error = str(e)
                self._create_error_news(resource, f"Ошибка OpenAI: {llm_error or 'Неизвестная ошибка'}")
                # Обновляем статистику при ошибке
                self._update_resource_statistics(
                    resource=resource,
                    news_count=0,
                    error_count=1,
                    is_no_news=False,
                    has_errors=True
                )
                return 0, 1, f"OpenAI API вернул ошибку: {llm_error}"
        else:
            error_msg = "Не настроен ни один провайдер LLM (Grok или OpenAI)"
            logger.error(error_msg)
            self._create_error_news(resource, error_msg)
            # Обновляем статистику при ошибке
            self._update_resource_statistics(
                resource=resource,
                news_count=0,
                error_count=1,
                is_no_news=False,
                has_errors=True
            )
            return 0, 1, error_msg
        
        # Если LLM не вернул ответ - создаем новость об ошибке
        if not llm_response:
            error_msg = f"{provider_used or 'LLM'} не вернул ответ: {llm_error or 'Неизвестная ошибка'}"
            self._create_error_news(resource, error_msg)
            # Обновляем статистику при ошибке
            self._update_resource_statistics(
                resource=resource,
                news_count=0,
                error_count=1,
                is_no_news=False,
                has_errors=True
            )
            return 0, 1, error_msg
        
        # Обрабатываем ответ от LLM
        final_news = []
        if isinstance(llm_response, dict) and 'news' in llm_response:
            final_news = llm_response['news']
        
        # Создаем новости
        created_count = 0
        error_count = 0
        is_no_news = False
        
        if not final_news or len(final_news) == 0:
            # Если новостей нет - создаем новость об этом
            self._create_no_news_news(resource, last_search_date, today)
            created_count = 1
            is_no_news = True
        else:
            for news_item in final_news:
                try:
                    self._create_news_post(news_item, resource)
                    created_count += 1
                except Exception as e:
                    logger.error(f"Error creating news post: {str(e)}")
                    error_count += 1
        
        # Обновляем статистику источника
        self._update_resource_statistics(
            resource=resource,
            news_count=created_count if not is_no_news else 0,
            error_count=error_count,
            is_no_news=is_no_news,
            has_errors=(error_count > 0 or llm_error is not None)
        )
        
        return created_count, error_count, None
    
    def _get_prompt_templates(self, language: str) -> Dict[str, str]:
        """Возвращает шаблоны промпта на указанном языке"""
        templates = {
            'ru': {
                'main': """Используй веб-поиск для поиска новостей на сайте {url} ({name}) за период с {start_date} по {end_date} включительно.

КРИТИЧЕСКИ ВАЖНО:
- Используй веб-поиск с запросом "site:{url}" с фильтрацией по дате
- Найди все новости, статьи, публикации, пресс-релизы, опубликованные на сайте {url} за указанный период
- Любая статья, публикация, пресс-релиз, новость, опубликованная на сайте за указанный период - это новость
- Для каждой найденной новости найди заголовок, краткое описание (1-2 абзаца) и ссылку на источник""",
                'period': "Период поиска: с {start_date} по {end_date} включительно.",
                'json_format': """Верни ответ СТРОГО в формате JSON (только JSON, без дополнительного текста):

{{
  "news": [
    {{
      "title": {{
        "ru": "Заголовок новости на русском",
        "en": "News title in English",
        "de": "Nachrichtentitel auf Deutsch",
        "pt": "Título da notícia em português"
      }},
      "summary": {{
        "ru": "Краткое описание новости на русском языке (1-2 абзаца)",
        "en": "Brief news summary in English (1-2 paragraphs)",
        "de": "Kurze Nachrichtenzusammenfassung auf Deutsch (1-2 Absätze)",
        "pt": "Resumo breve da notícia em português (1-2 parágrafos)"
      }},
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

Если новостей нет, верни: {{"news": []}}

Верни ТОЛЬКО JSON, без дополнительных комментариев или объяснений."""
            },
            'en': {
                'main': """Use web search to find all news on the website {url} ({name}) for the period from {start_date} to {end_date} inclusive.

CRITICALLY IMPORTANT:
- Use web search with query "site:{url}" with date filtering
- Find all news, articles, publications, press releases published on the website {url} for the specified period
- Any article, publication, press release, news published on the website for the specified period is news
- For each found news item, find the title, brief description (1-2 paragraphs) and source link""",
                'period': "Search period: from {start_date} to {end_date} inclusive.",
                'json_format': """Return the answer STRICTLY in JSON format (JSON only, without additional text):

{{
  "news": [
    {{
      "title": {{
        "ru": "Заголовок новости на русском",
        "en": "News title in English",
        "de": "Nachrichtentitel auf Deutsch",
        "pt": "Título da notícia em português"
      }},
      "summary": {{
        "ru": "Краткое описание новости на русском языке (1-2 абзаца)",
        "en": "Brief news summary in English (1-2 paragraphs)",
        "de": "Kurze Nachrichtenzusammenfassung auf Deutsch (1-2 Absätze)",
        "pt": "Resumo breve da notícia em português (1-2 parágrafos)"
      }},
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

If no news found, return: {{"news": []}}

Return ONLY JSON, without additional comments or explanations."""
            },
            'es': {
                'main': """Usa la búsqueda web para encontrar todas las noticias en el sitio web {url} ({name}) para el período del {start_date} al {end_date} inclusive.

CRÍTICAMENTE IMPORTANTE:
- Usa la búsqueda web con la consulta "site:{url}" con filtrado por fecha
- Encuentra todas las noticias, artículos, publicaciones, comunicados de prensa publicados en el sitio web {url} para el período especificado
- Cualquier artículo, publicación, comunicado de prensa, noticia publicada en el sitio web para el período especificado es noticia
- Para cada noticia encontrada, encuentra el título, descripción breve (1-2 párrafos) y enlace a la fuente""",
                'period': "Período de búsqueda: del {start_date} al {end_date} inclusive.",
                'json_format': """Devuelve la respuesta ESTRICTAMENTE en formato JSON (solo JSON, sin texto adicional):

{{
  "news": [
    {{
      "title": {{
        "ru": "Заголовок новости на русском",
        "en": "News title in English",
        "de": "Nachrichtentitel auf Deutsch",
        "pt": "Título da notícia em português"
      }},
      "summary": {{
        "ru": "Краткое описание новости на русском языке (1-2 абзаца)",
        "en": "Brief news summary in English (1-2 paragraphs)",
        "de": "Kurze Nachrichtenzusammenfassung auf Deutsch (1-2 Absätze)",
        "pt": "Resumo breve da notícia em português (1-2 parágrafos)"
      }},
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

Si no se encuentran noticias, devuelve: {{"news": []}}

Devuelve SOLO JSON, sin comentarios adicionales o explicaciones."""
            },
            'de': {
                'main': """Verwende die Websuche, um alle Nachrichten auf der Website {url} ({name}) für den Zeitraum vom {start_date} bis {end_date} einschließlich zu finden.

KRITISCH WICHTIG:
- Verwende die Websuche mit der Abfrage "site:{url}" mit Datumsfilterung
- Finde alle Nachrichten, Artikel, Veröffentlichungen, Pressemitteilungen, die auf der Website {url} für den angegebenen Zeitraum veröffentlicht wurden
- Jeder Artikel, jede Veröffentlichung, Pressemitteilung, Nachricht, die auf der Website für den angegebenen Zeitraum veröffentlicht wurde, ist eine Nachricht
- Finde für jede gefundene Nachricht den Titel, eine kurze Beschreibung (1-2 Absätze) und den Quelllink""",
                'period': "Suchzeitraum: vom {start_date} bis {end_date} einschließlich.",
                'json_format': """Gib die Antwort STRENG im JSON-Format zurück (nur JSON, ohne zusätzlichen Text):

{{
  "news": [
    {{
      "title": {{
        "ru": "Заголовок новости на русском",
        "en": "News title in English",
        "de": "Nachrichtentitel auf Deutsch",
        "pt": "Título da notícia em português"
      }},
      "summary": {{
        "ru": "Краткое описание новости на русском языке (1-2 абзаца)",
        "en": "Brief news summary in English (1-2 paragraphs)",
        "de": "Kurze Nachrichtenzusammenfassung auf Deutsch (1-2 Absätze)",
        "pt": "Resumo breve da notícia em português (1-2 parágrafos)"
      }},
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

Wenn keine Nachrichten gefunden wurden, gib zurück: {{"news": []}}

Gib NUR JSON zurück, ohne zusätzliche Kommentare oder Erklärungen."""
            },
            'pt': {
                'main': """Use a pesquisa na web para encontrar todas as notícias no site {url} ({name}) para o período de {start_date} a {end_date} inclusive.

CRITICAMENTE IMPORTANTE:
- Use a pesquisa na web com a consulta "site:{url}" com filtragem por data
- Encontre todas as notícias, artigos, publicações, comunicados de imprensa publicados no site {url} para o período especificado
- Qualquer artigo, publicação, comunicado de imprensa, notícia publicada no site para o período especificado é notícia
- Para cada notícia encontrada, encontre o título, descrição breve (1-2 parágrafos) e link da fonte""",
                'period': "Período de pesquisa: de {start_date} a {end_date} inclusive.",
                'json_format': """Retorne a resposta ESTRITAMENTE em formato JSON (apenas JSON, sem texto adicional):

{{
  "news": [
    {{
      "title": {{
        "ru": "Заголовок новости на русском",
        "en": "News title in English",
        "de": "Nachrichtentitel auf Deutsch",
        "pt": "Título da notícia em português"
      }},
      "summary": {{
        "ru": "Краткое описание новости на русском языке (1-2 абзаца)",
        "en": "Brief news summary in English (1-2 paragraphs)",
        "de": "Kurze Nachrichtenzusammenfassung auf Deutsch (1-2 Absätze)",
        "pt": "Resumo breve da notícia em português (1-2 parágrafos)"
      }},
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

Se nenhuma notícia for encontrada, retorne: {{"news": []}}

Retorne APENAS JSON, sem comentários adicionais ou explicações."""
            }
        }
        
        # По умолчанию используем английский, если язык не поддерживается
        return templates.get(language, templates['en'])
    
    def _build_search_prompt(self, resource: NewsResource, start_date: date, end_date: date) -> str:
        """Формирует промпт для поиска новостей на языке источника"""
        
        # Получаем язык источника (по умолчанию английский)
        language = getattr(resource, 'language', 'en') or 'en'
        templates = self._get_prompt_templates(language)
        
        # Форматируем даты в зависимости от языка
        if language == 'ru':
            start_date_str = start_date.strftime('%d.%m.%Y')
            end_date_str = end_date.strftime('%d.%m.%Y')
        else:
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
        
        # Если есть кастомные инструкции - используем их
        if resource.custom_search_instructions:
            return f"""{resource.custom_search_instructions}

{templates['period'].format(start_date=start_date_str, end_date=end_date_str)}
{templates['json_format']}"""

        # Стандартный промпт на языке источника
        return f"""{templates['main'].format(
            url=resource.url,
            name=resource.name,
            start_date=start_date_str,
            end_date=end_date_str
        )}
{templates['json_format']}"""

    def _query_openai(self, prompt: str) -> Optional[Dict]:
        """Запрос к OpenAI API с веб-поиском через Responses API"""
        if not self.openai_api_key:
            raise ValueError("OpenAI API key is not set")
        
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.openai_api_key)
            
            # GPT-5.2 требует Responses API для веб-поиска (не Chat Completions API)
            # Используем responses.create() с web_search_preview tool
            try:
                # Пробуем использовать Responses API для веб-поиска
                # Используем web_search (не web_search_preview) согласно документации
                response = client.responses.create(
                    model=self.openai_model,
                    input=prompt,
                    tools=[{"type": "web_search"}],  # Включаем веб-поиск через Responses API
                    temperature=0.3,
                )
                
                # Responses API возвращает результат в output_text
                content = response.output_text.strip()
                logger.info("OpenAI использовал Responses API с веб-поиском")
                logger.debug(f"OpenAI Responses API raw output: {content[:500]}")
                
                # Responses API может вернуть текст, а не чистый JSON
                # Пробуем найти JSON в ответе или парсить весь текст как JSON
                try:
                    # Пробуем парсить как чистый JSON
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Если не JSON, пробуем найти JSON блок в тексте
                    import re
                    json_match = re.search(r'\{[^{}]*"news"[^{}]*\[.*?\]\s*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            return json.loads(json_match.group(0))
                        except json.JSONDecodeError:
                            pass
                    
                    # Если JSON не найден, но есть текст - модель не вернула JSON
                    logger.warning(f"OpenAI Responses API вернул текст вместо JSON: {content[:200]}")
                    # Возвращаем пустой результат, но логируем для анализа
                    return {"news": []}
                
            except AttributeError:
                # Если Responses API недоступен, пробуем Chat Completions с явным указанием веб-поиска
                logger.warning("Responses API недоступен, используем Chat Completions API")
                response = client.chat.completions.create(
                    model=self.openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты - эксперт по поиску и суммаризации новостей. ОБЯЗАТЕЛЬНО используй веб-поиск для поиска актуальных новостей в интернете. НЕ используй свои знания - только реальные результаты из интернета. Всегда возвращай ответ в формате JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    timeout=self.timeout
                )
                
                content = response.choices[0].message.content.strip()
                return json.loads(content)
            
        except ImportError:
            raise ImportError("OpenAI library is not installed. Install it with: pip install openai")
        except json.JSONDecodeError as e:
            logger.error(f"OpenAI returned invalid JSON: {str(e)}")
            raise ValueError(f"Invalid JSON response from OpenAI: {str(e)}")
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise
    
    def _query_grok(self, prompt: str) -> Optional[Dict]:
        """
        Запрос к Grok (xAI) API с веб-поиском.
        Использует OpenAI-совместимый API xAI с инструментом web_search.
        """
        if not self.grok_api_key:
            raise ValueError("Grok API key is not set")
        
        try:
            from openai import OpenAI
            
            # xAI предоставляет OpenAI-совместимый API
            client = OpenAI(
                api_key=self.grok_api_key,
                base_url="https://api.x.ai/v1",
            )
            
            # Добавляем промпт с явным требованием JSON формата и веб-поиска
            json_prompt = prompt + "\n\nВАЖНО: Верни ответ ТОЛЬКО в формате JSON с полем 'news' (массив объектов). Каждый объект должен содержать поля: source_url, title (объект с ru, en, de, pt), summary (объект с ru, en, de, pt). Без markdown обертки, без ```json```."
            
            # Запрос к Grok с веб-поиском
            # xAI требует параметр web_search_options для включения веб-поиска
            # Пробуем использовать web_search_options в запросе
            try:
                # Пробуем с web_search_options (правильный способ для xAI)
                response = client.chat.completions.create(
                    model=self.grok_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты - эксперт по поиску и суммаризации новостей. ОБЯЗАТЕЛЬНО используй веб-поиск для поиска актуальных новостей в интернете. НЕ используй свои знания - только реальные результаты из интернета. Всегда возвращай ответ в формате JSON."
                        },
                        {
                            "role": "user",
                            "content": json_prompt
                        }
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    web_search_options={},  # Включаем веб-поиск
                    timeout=self.timeout
                )
            except TypeError:
                # Если web_search_options не поддерживается в этой версии SDK, пробуем без него
                logger.warning("web_search_options не поддерживается, пробуем без него")
                try:
                    response = client.chat.completions.create(
                        model=self.grok_model,
                        messages=[
                            {
                                "role": "system",
                                "content": "Ты - эксперт по поиску и суммаризации новостей. ОБЯЗАТЕЛЬНО используй веб-поиск для поиска актуальных новостей в интернете. НЕ используй свои знания - только реальные результаты из интернета. Всегда возвращай ответ в формате JSON."
                            },
                            {
                                "role": "user",
                                "content": json_prompt
                            }
                        ],
                        temperature=0.3,
                        response_format={"type": "json_object"},
                        timeout=self.timeout
                    )
                except Exception as e:
                    # Если запрос с response_format не работает, пробуем без него
                    logger.warning(f"Grok request with response_format failed: {str(e)}, trying without it")
                    response = client.chat.completions.create(
                        model=self.grok_model,
                        messages=[
                            {
                                "role": "system",
                                "content": "Ты - эксперт по поиску и суммаризации новостей. ОБЯЗАТЕЛЬНО используй веб-поиск для поиска актуальных новостей в интернете. НЕ используй свои знания - только реальные результаты из интернета. Всегда возвращай ответ в формате JSON."
                            },
                            {
                                "role": "user",
                                "content": json_prompt
                            }
                        ],
                        temperature=0.3,
                        timeout=self.timeout
                    )
            except Exception as e:
                # Если запрос с response_format не работает, пробуем без него
                logger.warning(f"Grok request with web_search_options failed: {str(e)}, trying without it")
                response = client.chat.completions.create(
                    model=self.grok_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты - эксперт по поиску и суммаризации новостей. ОБЯЗАТЕЛЬНО используй веб-поиск для поиска актуальных новостей в интернете. НЕ используй свои знания - только реальные результаты из интернета. Всегда возвращай ответ в формате JSON."
                        },
                        {
                            "role": "user",
                            "content": json_prompt
                        }
                    ],
                    temperature=0.3,
                    timeout=self.timeout
                )
            
            # Извлекаем контент
            content = response.choices[0].message.content.strip()
            
            logger.info(f"Grok использовал веб-поиск для запроса")
            logger.info(f"Grok raw output (первые 1000 символов): {content[:1000]}")
            
            # Логируем полный ответ для отладки
            if len(content) > 1000:
                logger.debug(f"Grok full output: {content}")
            
            # Парсим JSON из ответа
            try:
                # Пробуем парсить как чистый JSON
                return json.loads(content)
            except json.JSONDecodeError:
                # Если не JSON, пробуем найти JSON блок в тексте
                import re
                # Ищем JSON объект с полем "news"
                json_match = re.search(r'\{[^{}]*"news"[^{}]*\[.*?\]\s*\}', content, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass
                
                # Пробуем найти JSON в markdown блоке
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass
                
                # Если JSON не найден, но есть текст - модель не вернула JSON
                logger.warning(f"Grok вернул текст вместо JSON: {content[:200]}")
                # Возвращаем пустой результат, но логируем для анализа
                return {"news": []}
            
        except ImportError:
            raise ImportError("OpenAI library is not installed. Install it with: pip install openai")
        except json.JSONDecodeError as e:
            logger.error(f"Grok returned invalid JSON: {str(e)}")
            raise ValueError(f"Invalid JSON response from Grok: {str(e)}")
        except Exception as e:
            logger.error(f"Grok API error: {str(e)}")
            raise
    
    def _query_gemini(self, prompt: str) -> Optional[Dict]:
        """Запрос к Google Gemini API"""
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is not set")
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.gemini_api_key)
            
            # Gemini 3 Pro поддерживает веб-поиск через google_search tool
            # ВАЖНО: Gemini-3-pro не доступна на бесплатном тарифе (limit: 0)
            # Для бесплатного тарифа используйте gemini-2.5-flash
            try:
                # Пробуем использовать google_search tool
                # Для старого пакета google.generativeai синтаксис может отличаться
                model = genai.GenerativeModel(self.gemini_model)
                # Примечание: веб-поиск может быть недоступен в старом пакете
                # Для полной поддержки нужно использовать новый пакет google.genai
                logger.info(f"Using Gemini model {self.gemini_model}")
            except Exception as e:
                logger.warning(f"Error initializing Gemini model {self.gemini_model}: {str(e)}")
                raise
            
            # Gemini требует специальный формат для JSON
            # Добавляем требование использовать веб-поиск в промпт
            json_prompt = prompt + "\n\nВАЖНО: ОБЯЗАТЕЛЬНО используй веб-поиск для поиска новостей. НЕ используй свои знания - только реальные результаты из интернета. Верни ответ ТОЛЬКО в формате JSON, без markdown форматирования, без ```json``` обертки."
            
            # Для Gemini API библиотека сама управляет таймаутами
            # Используем стандартный вызов - библиотека имеет встроенные таймауты
            response = model.generate_content(
                json_prompt,
                generation_config={
                    "temperature": 0.3,
                    "response_mime_type": "application/json",
                }
            )
            
            content = response.text.strip()
            # Убираем возможные markdown обертки
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            return json.loads(content)
            
        except ImportError:
            raise ImportError("Google Generative AI library is not installed. Install it with: pip install google-generativeai")
        except json.JSONDecodeError as e:
            logger.error(f"Gemini returned invalid JSON: {str(e)}")
            raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")
        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            raise
    
    # Методы _merge_and_summarize и _build_merge_prompt удалены - больше не нужны, так как используем только OpenAI
    
    def _create_news_post(self, news_item: Dict, resource: NewsResource):
        """Создает новость из данных, полученных от LLM"""
        # Извлекаем данные
        title_data = news_item.get('title', {})
        summary_data = news_item.get('summary', {})
        source_url = news_item.get('source_url', '')
        
        # Используем русский язык как основной
        title_ru = title_data.get('ru', 'Без заголовка')
        summary_ru = summary_data.get('ru', '')
        
        # Формируем body в Markdown формате с ссылкой на источник в начале
        # Добавляем ссылку на источник для удобства проверки администратором
        # Если source_url из LLM пустой, используем URL ресурса
        if not source_url and resource:
            source_url = resource.url
        
        if source_url:
            resource_name = resource.name if resource else 'Источник'
            body_ru = f"**Источник для проверки:** [{resource_name}]({source_url})\n\n{summary_ru}"
        else:
            body_ru = summary_ru
        
        # Убеждаемся, что source_url всегда заполнен (используем URL ресурса если из LLM пустой)
        if not source_url and resource:
            source_url = resource.url
        
        # Создаем новость
        news_post = NewsPost.objects.create(
            title=title_ru,
            body=body_ru,
            source_url=source_url or '',  # Всегда сохраняем URL источника
            status='draft',
            source_language='ru',
            author=self.user,
            pub_date=timezone.now()
        )
        
        # Если есть переводы - сохраняем их через modeltranslation
        # (modeltranslation автоматически создаст поля title_en, title_de, title_pt и т.д.)
        for lang in self.SUPPORTED_LANGUAGES:
            if lang == 'ru':
                continue
            
            title_lang = title_data.get(lang, '')
            summary_lang = summary_data.get(lang, '')
            
            if title_lang:
                setattr(news_post, f'title_{lang}', title_lang)
            if summary_lang:
                setattr(news_post, f'body_{lang}', summary_lang)
        
        news_post.save()
        logger.info(f"Created news post: {news_post.id} - {title_ru}")
    
    def _create_no_news_news(self, resource: NewsResource, start_date: date, end_date: date):
        """Создает новость о том, что новостей не найдено"""
        title_ru = f"Новостей от источника '{resource.name}' не найдено"
        title_en = f"No news found from source '{resource.name}'"
        title_de = f"Keine Nachrichten von Quelle '{resource.name}' gefunden"
        title_pt = f"Nenhuma notícia encontrada da fonte '{resource.name}'"
        
        # Добавляем ссылку на источник в начало текста для удобства проверки
        body_ru = f"**Источник для проверки:** [{resource.name}]({resource.url})\n\nЗа период с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')} на ресурсе [{resource.name}]({resource.url}) новостей не обнаружено."
        body_en = f"**Source for verification:** [{resource.name}]({resource.url})\n\nFor the period from {start_date.strftime('%d.%m.%Y')} to {end_date.strftime('%d.%m.%Y')}, no news was found on the resource [{resource.name}]({resource.url})."
        body_de = f"**Quelle zur Überprüfung:** [{resource.name}]({resource.url})\n\nFür den Zeitraum vom {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')} wurden auf der Ressource [{resource.name}]({resource.url}) keine Nachrichten gefunden."
        body_pt = f"**Fonte para verificação:** [{resource.name}]({resource.url})\n\nNo período de {start_date.strftime('%d.%m.%Y')} a {end_date.strftime('%d.%m.%Y')}, nenhuma notícia foi encontrada no recurso [{resource.name}]({resource.url})."
        
        news_post = NewsPost.objects.create(
            title=title_ru,
            body=body_ru,
            source_url=resource.url,
            status='draft',
            source_language='ru',
            author=self.user,
            pub_date=timezone.now(),
            is_no_news_found=True  # Помечаем как запись "новостей не найдено"
        )
        
        # Устанавливаем переводы
        for lang in ['en', 'de', 'pt']:
            setattr(news_post, f'title_{lang}', locals()[f'title_{lang}'])
            setattr(news_post, f'body_{lang}', locals()[f'body_{lang}'])
        
        news_post.save()
        logger.info(f"Created 'no news' post for resource: {resource.id} (is_no_news_found=True)")
    
    def _create_error_news(self, resource: NewsResource, error_message: str):
        """Создает новость об ошибке при поиске"""
        title_ru = f"Ошибка при поиске новостей от источника '{resource.name}'"
        title_en = f"Error searching news from source '{resource.name}'"
        title_de = f"Fehler bei der Suche nach Nachrichten von Quelle '{resource.name}'"
        title_pt = f"Erro ao buscar notícias da fonte '{resource.name}'"
        
        # Добавляем ссылку на источник в начало текста для удобства проверки
        body_ru = f"**Источник для проверки:** [{resource.name}]({resource.url})\n\nПри попытке получить новости с ресурса [{resource.name}]({resource.url}) произошла ошибка:\n\n{error_message}"
        body_en = f"**Source for verification:** [{resource.name}]({resource.url})\n\nAn error occurred while trying to get news from resource [{resource.name}]({resource.url}):\n\n{error_message}"
        body_de = f"**Quelle zur Überprüfung:** [{resource.name}]({resource.url})\n\nBeim Versuch, Nachrichten von der Ressource [{resource.name}]({resource.url}) zu erhalten, ist ein Fehler aufgetreten:\n\n{error_message}"
        body_pt = f"**Fonte para verificação:** [{resource.name}]({resource.url})\n\nOcorreu um erro ao tentar obter notícias do recurso [{resource.name}]({resource.url}):\n\n{error_message}"
        
        news_post = NewsPost.objects.create(
            title=title_ru,
            body=body_ru,
            source_url=resource.url,
            status='draft',
            source_language='ru',
            author=self.user,
            pub_date=timezone.now()
        )
        
        # Устанавливаем переводы
        for lang in ['en', 'de', 'pt']:
            setattr(news_post, f'title_{lang}', locals()[f'title_{lang}'])
            setattr(news_post, f'body_{lang}', locals()[f'body_{lang}'])
        
        news_post.save()
        logger.info(f"Created error post for resource: {resource.id}")
    
    def _update_resource_statistics(
        self,
        resource: NewsResource,
        news_count: int,
        error_count: int,
        is_no_news: bool = False,
        has_errors: bool = False
    ):
        """
        Обновляет статистику источника после поиска новостей.
        
        Args:
            resource: Источник новостей
            news_count: Количество найденных новостей (реальных, не "не найдено")
            error_count: Количество ошибок при создании новостей
            is_no_news: Была ли создана запись "новостей не найдено"
            has_errors: Были ли ошибки API при поиске
        """
        try:
            from datetime import timedelta
            
            stats, created = NewsResourceStatistics.objects.get_or_create(
                resource=resource
            )
            
            now = timezone.now()
            
            # Обновляем счетчики
            stats.total_searches += 1
            stats.last_search_date = now
            
            if created:
                stats.first_search_date = now
            
            if has_errors or error_count > 0:
                stats.total_errors += 1
            elif is_no_news:
                stats.total_no_news += 1
            else:
                # Найдены реальные новости
                stats.total_news_found += news_count
                stats.last_news_date = now
            
            # Пересчитываем процентные метрики
            if stats.total_searches > 0:
                successful_searches = stats.total_searches - stats.total_no_news - stats.total_errors
                stats.success_rate = round((successful_searches / stats.total_searches) * 100, 2)
                stats.error_rate = round((stats.total_errors / stats.total_searches) * 100, 2)
                stats.avg_news_per_search = round(stats.total_news_found / stats.total_searches, 2)
            else:
                stats.success_rate = 0.0
                stats.error_rate = 0.0
                stats.avg_news_per_search = 0.0
            
            # Обновляем периодическую статистику (за последние 30 и 90 дней)
            thirty_days_ago = now - timedelta(days=30)
            ninety_days_ago = now - timedelta(days=90)
            
            # Подсчитываем новости за периоды из NewsPost
            from .models import NewsPost
            
            news_30d = NewsPost.objects.filter(
                source_url__icontains=resource.url,
                is_no_news_found=False,
                created_at__gte=thirty_days_ago
            ).count()
            
            news_90d = NewsPost.objects.filter(
                source_url__icontains=resource.url,
                is_no_news_found=False,
                created_at__gte=ninety_days_ago
            ).count()
            
            stats.news_last_30_days = news_30d
            stats.news_last_90_days = news_90d
            
            # Подсчитываем поиски за последние 30 дней
            # (можно улучшить, если хранить историю поисков отдельно)
            # Пока используем приблизительную оценку на основе last_search_date
            if stats.last_search_date and stats.last_search_date >= thirty_days_ago:
                stats.searches_last_30_days = min(stats.total_searches, stats.searches_last_30_days + 1)
            else:
                # Если последний поиск был давно, обнуляем счетчик
                stats.searches_last_30_days = 0
            
            # Пересчитываем рейтинг
            stats.ranking_score = stats.calculate_ranking_score()
            
            # Обновляем статус активности
            stats.update_active_status()
            
            # Обновляем приоритет (можно настроить логику)
            # Пока просто используем ranking_score как приоритет
            stats.priority = int(stats.ranking_score)
            
            stats.save()
            
            logger.debug(f"Updated statistics for resource {resource.id}: "
                        f"news={stats.total_news_found}, searches={stats.total_searches}, "
                        f"score={stats.ranking_score}")
            
        except Exception as e:
            # Не прерываем процесс поиска из-за ошибки статистики
            logger.error(f"Error updating statistics for resource {resource.id}: {str(e)}", exc_info=True)
    
    def discover_all_news(self, status_obj: Optional[NewsDiscoveryStatus] = None) -> Dict[str, int]:
        """
        Ищет новости для всех источников по очереди.
        При ошибке API перемещает источник в конец очереди и повторяет попытку.
        
        Источники типа 'manual' пропускаются - они требуют ручного ввода.
        
        Args:
            status_obj: Объект NewsDiscoveryStatus для отслеживания прогресса (опционально)
        
        Returns:
            Dict с статистикой: {'created': int, 'errors': int, 'total_processed': int, 'skipped_manual': int}
        """
        # Получаем только источники с автоматическим или гибридным поиском
        # Источники типа 'manual' пропускаются
        all_resources = NewsResource.objects.all().order_by('id')
        resources = list(all_resources.exclude(source_type=NewsResource.SOURCE_TYPE_MANUAL))
        skipped_manual = all_resources.filter(source_type=NewsResource.SOURCE_TYPE_MANUAL).count()
        
        if skipped_manual > 0:
            logger.info(f"Пропущено {skipped_manual} источников типа 'manual' (требуют ручного ввода)")
        
        total_created = 0
        total_errors = 0
        processed_count = 0
        
        # Обновляем статус с общим количеством источников
        if status_obj:
            status_obj.total_count = len(resources)
            status_obj.processed_count = 0
            status_obj.status = 'running'
            status_obj.save()
        
        # Обрабатываем источники с повторными попытками при ошибках
        retry_queue = []
        max_retries = 1  # Одна повторная попытка
        
        try:
            while resources or retry_queue:
                if not resources and retry_queue:
                    # Если основная очередь пуста, но есть источники для повтора
                    resources = retry_queue
                    retry_queue = []
                
                resource = resources.pop(0)
                processed_count += 1
                
                # Обновляем прогресс
                if status_obj:
                    status_obj.processed_count = processed_count
                    status_obj.save()
                
                try:
                    created, errors, error_msg = self.discover_news_for_resource(resource)
                    total_created += created
                    total_errors += errors
                    
                    if error_msg and resource not in retry_queue:
                        # Если была ошибка API - добавляем в очередь для повтора
                        retry_queue.append(resource)
                        logger.info(f"Resource {resource.id} added to retry queue due to API error")
                    
                except Exception as e:
                    logger.error(f"Unexpected error processing resource {resource.id}: {str(e)}")
                    total_errors += 1
                    if resource not in retry_queue:
                        retry_queue.append(resource)
            
            # Обновляем дату последнего поиска
            NewsDiscoveryRun.update_last_search_date(timezone.now().date())
            
            # Обновляем статус на завершенный
            if status_obj:
                status_obj.status = 'completed'
                status_obj.save()
        
        except Exception as e:
            logger.error(f"Critical error in discover_all_news: {str(e)}")
            if status_obj:
                status_obj.status = 'error'
                status_obj.save()
            raise
        
        return {
            'created': total_created,
            'errors': total_errors,
            'total_processed': processed_count,
            'skipped_manual': skipped_manual
        }
    
    # ==================== МЕТОДЫ ДЛЯ ПОИСКА ПО ПРОИЗВОДИТЕЛЯМ ====================
    
    def discover_news_for_manufacturer(self, manufacturer: Manufacturer) -> Tuple[int, int, Optional[str]]:
        """
        Ищет новости о производителе в интернете.
        
        Args:
            manufacturer: Производитель
            
        Returns:
            Tuple[created_count, error_count, error_message]
        """
        # Получаем период поиска
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        
        # Формируем промпт для LLM
        prompt = self._build_manufacturer_search_prompt(manufacturer, last_search_date, today)
        
        # Получаем ответ от LLM (Grok как основной, OpenAI как резервный)
        llm_response = None
        llm_error = None
        provider_used = None
        
        # Пробуем сначала Grok, если включен
        if self.use_grok and self.grok_api_key:
            try:
                logger.info(f"[Grok] Начинаю обработку производителя {manufacturer.id} ({manufacturer.name})")
                llm_response = self._query_grok(prompt)
                provider_used = 'Grok'
                logger.info(f"[Grok] ✅ Успешно обработал производителя {manufacturer.id} ({manufacturer.name})")
            except Exception as e:
                logger.warning(f"[Grok] ❌ Ошибка для производителя {manufacturer.id}: {str(e)}")
                llm_error = f"Grok: {str(e)}"
                # Если есть fallback на OpenAI - пробуем его
                if self.use_openai_fallback and self.openai_api_key:
                    try:
                        logger.info(f"[OpenAI Fallback] Пробую обработать производителя {manufacturer.id} ({manufacturer.name})")
                        llm_response = self._query_openai(prompt)
                        provider_used = 'OpenAI (fallback)'
                        logger.info(f"[OpenAI Fallback] ✅ Успешно обработал производителя {manufacturer.id} ({manufacturer.name})")
                    except Exception as e2:
                        logger.error(f"[OpenAI Fallback] ❌ Ошибка для производителя {manufacturer.id}: {str(e2)}")
                        llm_error = f"{llm_error}; OpenAI fallback: {str(e2)}"
                        self._create_error_manufacturer(manufacturer, f"Ошибка обоих провайдеров: {llm_error}")
                        # Обновляем статистику при ошибке
                        self._update_manufacturer_statistics(
                            manufacturer=manufacturer,
                            news_count=0,
                            error_count=1,
                            is_no_news=False,
                            has_errors=True
                        )
                        return 0, 1, f"Ошибка обоих провайдеров: {llm_error}"
        # Если Grok не используется или нет ключа - используем OpenAI
        elif self.openai_api_key:
            try:
                llm_response = self._query_openai(prompt)
                provider_used = 'OpenAI'
                logger.info(f"OpenAI успешно обработал производителя {manufacturer.id}")
            except Exception as e:
                logger.error(f"OpenAI error for manufacturer {manufacturer.id}: {str(e)}")
                llm_error = str(e)
                self._create_error_manufacturer(manufacturer, f"Ошибка OpenAI: {llm_error or 'Неизвестная ошибка'}")
                # Обновляем статистику при ошибке
                self._update_manufacturer_statistics(
                    manufacturer=manufacturer,
                    news_count=0,
                    error_count=1,
                    is_no_news=False,
                    has_errors=True
                )
                return 0, 1, f"OpenAI API вернул ошибку: {llm_error}"
        else:
            error_msg = "Не настроен ни один провайдер LLM (Grok или OpenAI)"
            logger.error(error_msg)
            self._create_error_manufacturer(manufacturer, error_msg)
            # Обновляем статистику при ошибке
            self._update_manufacturer_statistics(
                manufacturer=manufacturer,
                news_count=0,
                error_count=1,
                is_no_news=False,
                has_errors=True
            )
            return 0, 1, error_msg
        
        # Если LLM не вернул ответ - создаем новость об ошибке
        if not llm_response:
            error_msg = f"{provider_used or 'LLM'} не вернул ответ: {llm_error or 'Неизвестная ошибка'}"
            self._create_error_manufacturer(manufacturer, error_msg)
            # Обновляем статистику при ошибке
            self._update_manufacturer_statistics(
                manufacturer=manufacturer,
                news_count=0,
                error_count=1,
                is_no_news=False,
                has_errors=True
            )
            return 0, 1, error_msg
        
        # Обрабатываем ответ от LLM
        final_news = []
        if isinstance(llm_response, dict) and 'news' in llm_response:
            final_news = llm_response['news']
        
        # Создаем новости
        created_count = 0
        error_count = 0
        is_no_news = False
        
        if not final_news or len(final_news) == 0:
            # Если новостей нет - создаем новость об этом
            self._create_no_news_manufacturer(manufacturer, last_search_date, today)
            created_count = 1
            is_no_news = True
        else:
            for news_item in final_news:
                try:
                    self._create_manufacturer_news_post(news_item, manufacturer)
                    created_count += 1
                except Exception as e:
                    logger.error(f"Error creating news post for manufacturer: {str(e)}")
                    error_count += 1
        
        # Обновляем статистику производителя
        self._update_manufacturer_statistics(
            manufacturer=manufacturer,
            news_count=created_count if not is_no_news else 0,
            error_count=error_count,
            is_no_news=is_no_news,
            has_errors=(error_count > 0 or llm_error is not None)
        )
        
        return created_count, error_count, None
    
    def _build_manufacturer_search_prompt(self, manufacturer: Manufacturer, start_date: date, end_date: date) -> str:
        """Формирует промпт для поиска новостей на сайтах производителя"""
        # Собираем все сайты производителя
        websites = []
        if manufacturer.website_1:
            websites.append(manufacturer.website_1)
        if manufacturer.website_2:
            websites.append(manufacturer.website_2)
        if manufacturer.website_3:
            websites.append(manufacturer.website_3)
        
        if not websites:
            # Если нет сайтов - используем английский промпт (производители международные)
            templates = self._get_prompt_templates('en')
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
            
            return f"""Use web search to find news about manufacturer {manufacturer.name} for the period from {start_date_str} to {end_date_str} inclusive.

CRITICALLY IMPORTANT:
- Manufacturer {manufacturer.name} has no official websites specified
- Search for news about manufacturer {manufacturer.name} on the internet
- Use web search with query "{manufacturer.name}" HVAC news with date filtering
- Find all news, articles, publications, press releases about the manufacturer published for the specified period
- Any article, publication, press release, news about the manufacturer published for the specified period is news
- For each found news item, find the title, brief description (1-2 paragraphs) and source link
- News can be on any websites: industry publications, news portals, press releases, etc.
{templates['json_format']}"""
        
        websites_str = ", ".join(websites)
        templates = self._get_prompt_templates('en')
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        return f"""Use web search to find news on the official websites of manufacturer {manufacturer.name} for the period from {start_date_str} to {end_date_str} inclusive.

CRITICALLY IMPORTANT:
- Official manufacturer websites: {websites_str}
- For each website, use web search with query "site:[URL]" with date filtering
- Find all news, articles, publications, press releases published on these websites for the specified period
- Any article, publication, press release, news published on the official manufacturer websites for the specified period is news
- For each found news item, find the title, brief description (1-2 paragraphs) and source link
{templates['json_format']}"""
    
    def _create_manufacturer_news_post(self, news_item: Dict, manufacturer: Manufacturer):
        """Создает новость о производителе из данных, полученных от LLM"""
        # Извлекаем данные
        title_data = news_item.get('title', {})
        summary_data = news_item.get('summary', {})
        source_url = news_item.get('source_url', '')
        
        # Используем русский язык как основной
        title_ru = title_data.get('ru', 'Без заголовка')
        summary_ru = summary_data.get('ru', '')
        
        # Формируем body в Markdown формате с ссылкой на источник в начале
        if not source_url:
            # Если source_url пустой, используем первый сайт производителя
            source_url = manufacturer.website_1 or ''
        
        body_ru = f"**Источник для проверки:** [{source_url}]({source_url})\n\n" if source_url else ""
        body_ru += summary_ru
        
        # Создаем новость
        news_post = NewsPost.objects.create(
            title=title_ru,
            body=body_ru,
            source_url=source_url,
            manufacturer=manufacturer,  # Связываем с производителем
            status='draft',
            source_language='ru',
            author=self.user,
            pub_date=timezone.now()
        )
        
        # Устанавливаем переводы
        for lang in ['en', 'de', 'pt']:
            title_lang = title_data.get(lang, '')
            summary_lang = summary_data.get(lang, '')
            
            if title_lang:
                setattr(news_post, f'title_{lang}', title_lang)
            if summary_lang:
                body_lang = f"**Source for verification:** [{source_url}]({source_url})\n\n" if source_url else ""
                body_lang += summary_lang
                setattr(news_post, f'body_{lang}', body_lang)
        
        news_post.save()
        logger.info(f"Created news post for manufacturer {manufacturer.id}: {news_post.id} - {title_ru}")
    
    def _create_no_news_manufacturer(self, manufacturer: Manufacturer, start_date: date, end_date: date):
        """Создает новость о том, что новостей о производителе не найдено"""
        title_ru = f"Новостей о производителе '{manufacturer.name}' не найдено"
        title_en = f"No news found about manufacturer '{manufacturer.name}'"
        title_de = f"Keine Nachrichten über Hersteller '{manufacturer.name}' gefunden"
        title_pt = f"Nenhuma notícia encontrada sobre o fabricante '{manufacturer.name}'"
        
        # Собираем сайты производителя
        websites = []
        if manufacturer.website_1:
            websites.append(manufacturer.website_1)
        if manufacturer.website_2:
            websites.append(manufacturer.website_2)
        if manufacturer.website_3:
            websites.append(manufacturer.website_3)
        
        websites_str = ", ".join([f"[{url}]({url})" for url in websites]) if websites else "нет указанных сайтов"
        source_url = manufacturer.website_1 or ''
        
        body_ru = f"**Производитель для проверки:** {manufacturer.name}\n"
        body_ru += f"**Сайты производителя:** {websites_str}\n\n"
        body_ru += f"За период с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')} новостей о производителе {manufacturer.name} не обнаружено."
        
        body_en = f"**Manufacturer for verification:** {manufacturer.name}\n"
        body_en += f"**Manufacturer websites:** {websites_str}\n\n"
        body_en += f"For the period from {start_date.strftime('%d.%m.%Y')} to {end_date.strftime('%d.%m.%Y')}, no news was found about manufacturer {manufacturer.name}."
        
        body_de = f"**Hersteller zur Überprüfung:** {manufacturer.name}\n"
        body_de += f"**Hersteller-Websites:** {websites_str}\n\n"
        body_de += f"Für den Zeitraum vom {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')} wurden keine Nachrichten über Hersteller {manufacturer.name} gefunden."
        
        body_pt = f"**Fabricante para verificação:** {manufacturer.name}\n"
        body_pt += f"**Sites do fabricante:** {websites_str}\n\n"
        body_pt += f"No período de {start_date.strftime('%d.%m.%Y')} a {end_date.strftime('%d.%m.%Y')}, nenhuma notícia foi encontrada sobre o fabricante {manufacturer.name}."
        
        news_post = NewsPost.objects.create(
            title=title_ru,
            body=body_ru,
            source_url=source_url,
            manufacturer=manufacturer,
            is_no_news_found=True,  # Помечаем как запись "новостей не найдено"
            status='draft',
            source_language='ru',
            author=self.user,
            pub_date=timezone.now()
        )
        
        # Устанавливаем переводы
        for lang in ['en', 'de', 'pt']:
            setattr(news_post, f'title_{lang}', locals()[f'title_{lang}'])
            setattr(news_post, f'body_{lang}', locals()[f'body_{lang}'])
        
        news_post.save()
        logger.info(f"Created 'no news' post for manufacturer: {manufacturer.id}")
    
    def _create_error_manufacturer(self, manufacturer: Manufacturer, error_message: str):
        """Создает новость об ошибке при поиске новостей о производителе"""
        title_ru = f"Ошибка при поиске новостей о производителе '{manufacturer.name}'"
        title_en = f"Error searching news about manufacturer '{manufacturer.name}'"
        title_de = f"Fehler bei der Suche nach Nachrichten über Hersteller '{manufacturer.name}'"
        title_pt = f"Erro ao buscar notícias sobre o fabricante '{manufacturer.name}'"
        
        # Собираем сайты производителя
        websites = []
        if manufacturer.website_1:
            websites.append(manufacturer.website_1)
        if manufacturer.website_2:
            websites.append(manufacturer.website_2)
        if manufacturer.website_3:
            websites.append(manufacturer.website_3)
        
        websites_str = ", ".join([f"[{url}]({url})" for url in websites]) if websites else "нет указанных сайтов"
        source_url = manufacturer.website_1 or ''
        
        body_ru = f"**Производитель для проверки:** {manufacturer.name}\n"
        body_ru += f"**Сайты производителя:** {websites_str}\n\n"
        body_ru += f"При попытке получить новости о производителе {manufacturer.name} произошла ошибка:\n\n{error_message}"
        
        body_en = f"**Manufacturer for verification:** {manufacturer.name}\n"
        body_en += f"**Manufacturer websites:** {websites_str}\n\n"
        body_en += f"An error occurred while trying to get news about manufacturer {manufacturer.name}:\n\n{error_message}"
        
        body_de = f"**Hersteller zur Überprüfung:** {manufacturer.name}\n"
        body_de += f"**Hersteller-Websites:** {websites_str}\n\n"
        body_de += f"Beim Versuch, Nachrichten über Hersteller {manufacturer.name} zu erhalten, ist ein Fehler aufgetreten:\n\n{error_message}"
        
        body_pt = f"**Fabricante para verificação:** {manufacturer.name}\n"
        body_pt += f"**Sites do fabricante:** {websites_str}\n\n"
        body_pt += f"Ocorreu um erro ao tentar obter notícias sobre o fabricante {manufacturer.name}:\n\n{error_message}"
        
        news_post = NewsPost.objects.create(
            title=title_ru,
            body=body_ru,
            source_url=source_url,
            manufacturer=manufacturer,
            status='draft',
            source_language='ru',
            author=self.user,
            pub_date=timezone.now()
        )
        
        # Устанавливаем переводы
        for lang in ['en', 'de', 'pt']:
            setattr(news_post, f'title_{lang}', locals()[f'title_{lang}'])
            setattr(news_post, f'body_{lang}', locals()[f'body_{lang}'])
        
        news_post.save()
        logger.info(f"Created error post for manufacturer: {manufacturer.id}")
    
    def _update_manufacturer_statistics(
        self,
        manufacturer: Manufacturer,
        news_count: int,
        error_count: int,
        is_no_news: bool = False,
        has_errors: bool = False
    ):
        """
        Обновляет статистику производителя после поиска новостей.
        
        Args:
            manufacturer: Производитель
            news_count: Количество найденных новостей (реальных, не "не найдено")
            error_count: Количество ошибок при создании новостей
            is_no_news: Была ли создана запись "новостей не найдено"
            has_errors: Были ли ошибки API при поиске
        """
        try:
            from datetime import timedelta
            
            stats, created = ManufacturerStatistics.objects.get_or_create(
                manufacturer=manufacturer
            )
            
            now = timezone.now()
            
            # Обновляем счетчики
            stats.total_searches += 1
            stats.last_search_date = now
            
            if created:
                stats.first_search_date = now
            
            if has_errors or error_count > 0:
                stats.total_errors += 1
            elif is_no_news:
                stats.total_no_news += 1
            else:
                # Найдены реальные новости
                stats.total_news_found += news_count
                stats.last_news_date = now
            
            # Пересчитываем процентные метрики
            if stats.total_searches > 0:
                successful_searches = stats.total_searches - stats.total_no_news - stats.total_errors
                stats.success_rate = round((successful_searches / stats.total_searches) * 100, 2)
                stats.error_rate = round((stats.total_errors / stats.total_searches) * 100, 2)
                stats.avg_news_per_search = round(stats.total_news_found / stats.total_searches, 2)
            else:
                stats.success_rate = 0.0
                stats.error_rate = 0.0
                stats.avg_news_per_search = 0.0
            
            # Обновляем периодическую статистику (за последние 30 и 90 дней)
            thirty_days_ago = now - timedelta(days=30)
            ninety_days_ago = now - timedelta(days=90)
            
            # Подсчитываем новости за периоды из NewsPost
            news_30d = NewsPost.objects.filter(
                manufacturer=manufacturer,
                is_no_news_found=False,
                created_at__gte=thirty_days_ago
            ).count()
            
            news_90d = NewsPost.objects.filter(
                manufacturer=manufacturer,
                is_no_news_found=False,
                created_at__gte=ninety_days_ago
            ).count()
            
            stats.news_last_30_days = news_30d
            stats.news_last_90_days = news_90d
            
            # Подсчитываем поиски за последние 30 дней
            if stats.last_search_date and stats.last_search_date >= thirty_days_ago:
                stats.searches_last_30_days = min(stats.total_searches, stats.searches_last_30_days + 1)
            else:
                stats.searches_last_30_days = 0
            
            # Пересчитываем рейтинг
            stats.ranking_score = stats.calculate_ranking_score()
            
            # Обновляем статус активности
            stats.update_active_status()
            
            # Обновляем приоритет
            stats.priority = int(stats.ranking_score)
            
            stats.save()
            
            logger.debug(f"Updated statistics for manufacturer {manufacturer.id}: "
                        f"news={stats.total_news_found}, searches={stats.total_searches}, "
                        f"score={stats.ranking_score}")
            
        except Exception as e:
            # Не прерываем процесс поиска из-за ошибки статистики
            logger.error(f"Error updating statistics for manufacturer {manufacturer.id}: {str(e)}", exc_info=True)
    
    def discover_all_manufacturers_news(self, status_obj: Optional[NewsDiscoveryStatus] = None) -> Dict[str, int]:
        """
        Ищет новости для всех производителей по очереди.
        При ошибке API перемещает производителя в конец очереди и повторяет попытку.
        
        Args:
            status_obj: Объект NewsDiscoveryStatus для отслеживания прогресса (опционально)
        
        Returns:
            Dict с статистикой: {'created': int, 'errors': int, 'total_processed': int}
        """
        manufacturers = list(Manufacturer.objects.all().order_by('id'))
        total_created = 0
        total_errors = 0
        processed_count = 0
        
        # Обновляем статус с общим количеством производителей
        if status_obj:
            status_obj.total_count = len(manufacturers)
            status_obj.processed_count = 0
            status_obj.status = 'running'
            status_obj.save()
        
        # Обрабатываем производителей с повторными попытками при ошибках
        retry_queue = []
        max_retries = 1  # Одна повторная попытка
        
        try:
            while manufacturers or retry_queue:
                if not manufacturers and retry_queue:
                    # Если основная очередь пуста, но есть производители для повтора
                    manufacturers = retry_queue
                    retry_queue = []
                
                manufacturer = manufacturers.pop(0)
                processed_count += 1
                
                # Обновляем прогресс
                if status_obj:
                    status_obj.processed_count = processed_count
                    status_obj.save()
                
                try:
                    created, errors, error_msg = self.discover_news_for_manufacturer(manufacturer)
                    total_created += created
                    total_errors += errors
                    
                    if error_msg and manufacturer not in retry_queue:
                        # Если была ошибка API - добавляем в очередь для повтора
                        retry_queue.append(manufacturer)
                        logger.info(f"Manufacturer {manufacturer.id} added to retry queue due to API error")
                    
                except Exception as e:
                    logger.error(f"Unexpected error processing manufacturer {manufacturer.id}: {str(e)}")
                    total_errors += 1
                    if manufacturer not in retry_queue:
                        retry_queue.append(manufacturer)
            
            # Обновляем статус на завершенный
            if status_obj:
                status_obj.status = 'completed'
                status_obj.save()
        
        except Exception as e:
            logger.error(f"Critical error in discover_all_manufacturers_news: {str(e)}")
            if status_obj:
                status_obj.status = 'error'
                status_obj.save()
            raise
        
        return {
            'created': total_created,
            'errors': total_errors,
            'total_processed': processed_count
        }
