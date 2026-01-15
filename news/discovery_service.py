"""
Сервис для автоматического поиска новостей через LLM API.
Использует Grok 4.1 Fast (xAI) с встроенным веб-поиском как основной провайдер.
Anthropic Claude Haiku 4.5 используется как дополнительный провайдер.
OpenAI GPT-5.2 с Responses API используется как резервный вариант.
"""
import logging
import json
import re
from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
from urllib.parse import urlparse
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from references.models import NewsResource, NewsResourceStatistics, Manufacturer, ManufacturerStatistics
from .models import NewsPost, NewsDiscoveryRun, NewsDiscoveryStatus, SearchConfiguration, DiscoveryAPICall
from users.models import User
import time

logger = logging.getLogger(__name__)


class NewsDiscoveryService:
    """
    Сервис для автоматического поиска новостей через LLM API.
    Загружает конфигурацию из БД для гибкой настройки без изменения кода.
    """
    
    SUPPORTED_LANGUAGES = ['ru', 'en', 'de', 'pt']
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """
        Извлекает домен из URL для использования в поиске site:
        Примеры:
        - https://www.ejarn.com/category/eJarn_news_index -> ejarn.com
        - https://ejarn.com/news -> ejarn.com
        - http://www.example.com/path -> example.com
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            # Убираем www. если есть
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            # Если не удалось распарсить, пробуем извлечь вручную
            # Убираем протокол
            domain = re.sub(r'^https?://', '', url)
            # Убираем путь
            domain = domain.split('/')[0]
            # Убираем www.
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
    
    def __init__(self, user: Optional[User] = None, config: Optional[SearchConfiguration] = None):
        self.user = user
        
        # Загружаем конфигурацию из БД или используем переданную
        self.config = config or SearchConfiguration.get_active()
        
        # API ключи всегда из settings (безопасность)
        self.openai_api_key = getattr(settings, 'TRANSLATION_API_KEY', '')
        self.grok_api_key = getattr(settings, 'XAI_API_KEY', '')
        self.anthropic_api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
        self.gemini_api_key = getattr(settings, 'GEMINI_API_KEY', '')
        
        # Модели из конфигурации
        self.openai_model = self.config.openai_model
        self.grok_model = self.config.grok_model
        self.anthropic_model = self.config.anthropic_model
        self.gemini_model = self.config.gemini_model
        
        # Параметры из конфигурации
        self.timeout = self.config.timeout
        self.temperature = self.config.temperature
        self.max_search_results = self.config.max_search_results
        self.search_context_size = self.config.search_context_size
        self.max_news_per_resource = self.config.max_news_per_resource
        self.delay_between_requests = self.config.delay_between_requests
        
        # Определяем какие провайдеры использовать
        self.primary_provider = self.config.primary_provider
        self.fallback_chain = self.config.fallback_chain or []
        
        # Для совместимости со старым кодом
        self.use_grok = self.primary_provider == 'grok' or 'grok' in self.fallback_chain
        self.use_anthropic = self.primary_provider == 'anthropic' or 'anthropic' in self.fallback_chain
        self.use_openai_fallback = 'openai' in self.fallback_chain
        self.anthropic_priority = 2  # Deprecated, используем fallback_chain
        
        # Текущий запуск поиска (для трекинга метрик)
        self.current_run: Optional[NewsDiscoveryRun] = None
        self.current_resource: Optional[NewsResource] = None
        self.current_manufacturer: Optional[Manufacturer] = None
    
    def start_discovery_run(self) -> NewsDiscoveryRun:
        """Начинает новый запуск поиска с текущей конфигурацией"""
        self.current_run = NewsDiscoveryRun.start_new_run(self.config)
        logger.info(f"Started discovery run #{self.current_run.id} with config '{self.config.name}'")
        return self.current_run
    
    def finish_discovery_run(self):
        """Завершает текущий запуск поиска"""
        if self.current_run:
            self.current_run.finish()
            logger.info(f"Finished discovery run #{self.current_run.id}: "
                       f"{self.current_run.news_found} news, ${self.current_run.estimated_cost_usd:.4f}")
    
    def _track_api_call(self, provider: str, model: str, input_tokens: int, output_tokens: int,
                        duration_ms: int, success: bool, error_message: str = '', 
                        news_extracted: int = 0) -> float:
        """
        Отслеживает вызов API и рассчитывает стоимость.
        Возвращает стоимость вызова в USD.
        """
        # Рассчитываем стоимость
        input_price = self.config.get_price(provider, 'input')
        output_price = self.config.get_price(provider, 'output')
        cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
        
        # Записываем в детальную историю
        if self.current_run:
            DiscoveryAPICall.objects.create(
                discovery_run=self.current_run,
                resource=self.current_resource,
                manufacturer=self.current_manufacturer,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                duration_ms=duration_ms,
                success=success,
                error_message=error_message,
                news_extracted=news_extracted
            )
            
            # Обновляем агрегированную статистику
            self.current_run.add_api_call(provider, input_tokens, output_tokens, cost, success)
        
        return cost
    
    def discover_news_for_resource(self, resource: NewsResource, provider: str = 'auto') -> Tuple[int, int, Optional[str]]:
        """
        Ищет новости для одного источника.
        
        Args:
            resource: Источник новостей
            provider: Провайдер LLM ('auto', 'grok', 'anthropic', 'openai')
            
        Returns:
            Tuple[created_count, error_count, error_message]
        """
        # Получаем период поиска
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        
        # Формируем промпт для LLM
        prompt = self._build_search_prompt(resource, last_search_date, today)
        
        # Извлекаем домен для ограничения веб-поиска
        domain = self._extract_domain(resource.url)
        
        # Получаем ответ от LLM (с учетом выбранного провайдера)
        llm_response = None
        llm_error = None
        provider_used = None
        errors_chain = []
        
        # Если provider='auto' - используем цепочку провайдеров
        if provider == 'auto':
            # Пробуем сначала Grok, если включен
            if self.use_grok and self.grok_api_key:
                try:
                    logger.info(f"[Grok] Начинаю обработку ресурса {resource.id} ({resource.name})")
                    llm_response = self._query_grok(prompt, domain=domain)
                    provider_used = 'Grok'
                    logger.info(f"[Grok] ✅ Успешно обработал ресурс {resource.id} ({resource.name})")
                except Exception as e:
                    logger.warning(f"[Grok] ❌ Ошибка для ресурса {resource.id}: {str(e)}")
                    errors_chain.append(f"Grok: {str(e)}")
                    llm_error = "; ".join(errors_chain)
            
            # Если Grok не сработал, пробуем Anthropic (если включен)
            if not llm_response and self.use_anthropic and self.anthropic_api_key:
                try:
                    logger.info(f"[Anthropic] Пробую обработать ресурс {resource.id} ({resource.name})")
                    llm_response = self._query_anthropic(prompt)
                    provider_used = 'Anthropic'
                    logger.info(f"[Anthropic] ✅ Успешно обработал ресурс {resource.id} ({resource.name})")
                except Exception as e:
                    logger.warning(f"[Anthropic] ❌ Ошибка для ресурса {resource.id}: {str(e)}")
                    errors_chain.append(f"Anthropic: {str(e)}")
                    llm_error = "; ".join(errors_chain)
            
            # Если Grok и Anthropic не сработали, пробуем OpenAI как резервный
            if not llm_response and self.use_openai_fallback and self.openai_api_key:
                try:
                    logger.info(f"[OpenAI Fallback] Пробую обработать ресурс {resource.id} ({resource.name})")
                    llm_response = self._query_openai(prompt)
                    provider_used = 'OpenAI (fallback)'
                    logger.info(f"[OpenAI Fallback] ✅ Успешно обработал ресурс {resource.id} ({resource.name})")
                except Exception as e:
                    logger.error(f"[OpenAI Fallback] ❌ Ошибка для ресурса {resource.id}: {str(e)}")
                    errors_chain.append(f"OpenAI fallback: {str(e)}")
                    llm_error = "; ".join(errors_chain)
        else:
            # Используем конкретный провайдер
            if provider == 'grok':
                if not self.grok_api_key:
                    error_msg = "Grok API key не настроен"
                    logger.error(f"❌ {error_msg} для ресурса {resource.id}")
                    self._create_error_news(resource, error_msg)
                    return 0, 1, error_msg
                try:
                    logger.info(f"[Grok] Начинаю обработку ресурса {resource.id} ({resource.name})")
                    llm_response = self._query_grok(prompt, domain=domain)
                    provider_used = 'Grok'
                    logger.info(f"[Grok] ✅ Успешно обработал ресурс {resource.id} ({resource.name})")
                except Exception as e:
                    error_msg = f"Ошибка Grok: {str(e)}"
                    logger.error(f"❌ {error_msg} для ресурса {resource.id}")
                    self._create_error_news(resource, error_msg)
                    self._update_resource_statistics(
                        resource=resource,
                        news_count=0,
                        error_count=1,
                        is_no_news=False,
                        has_errors=True
                    )
                    return 0, 1, error_msg
            
            elif provider == 'anthropic':
                if not self.anthropic_api_key:
                    error_msg = "Anthropic API key не настроен"
                    logger.error(f"❌ {error_msg} для ресурса {resource.id}")
                    self._create_error_news(resource, error_msg)
                    return 0, 1, error_msg
                try:
                    logger.info(f"[Anthropic] Начинаю обработку ресурса {resource.id} ({resource.name})")
                    llm_response = self._query_anthropic(prompt)
                    provider_used = 'Anthropic'
                    logger.info(f"[Anthropic] ✅ Успешно обработал ресурс {resource.id} ({resource.name})")
                except Exception as e:
                    error_msg = f"Ошибка Anthropic: {str(e)}"
                    logger.error(f"❌ {error_msg} для ресурса {resource.id}")
                    self._create_error_news(resource, error_msg)
                    self._update_resource_statistics(
                        resource=resource,
                        news_count=0,
                        error_count=1,
                        is_no_news=False,
                        has_errors=True
                    )
                    return 0, 1, error_msg
            
            elif provider == 'openai':
                if not self.openai_api_key:
                    error_msg = "OpenAI API key не настроен"
                    logger.error(f"❌ {error_msg} для ресурса {resource.id}")
                    self._create_error_news(resource, error_msg)
                    return 0, 1, error_msg
                try:
                    logger.info(f"[OpenAI] Начинаю обработку ресурса {resource.id} ({resource.name})")
                    llm_response = self._query_openai(prompt)
                    provider_used = 'OpenAI'
                    logger.info(f"[OpenAI] ✅ Успешно обработал ресурс {resource.id} ({resource.name})")
                except Exception as e:
                    error_msg = f"Ошибка OpenAI: {str(e)}"
                    logger.error(f"❌ {error_msg} для ресурса {resource.id}")
                    self._create_error_news(resource, error_msg)
                    self._update_resource_statistics(
                        resource=resource,
                        news_count=0,
                        error_count=1,
                        is_no_news=False,
                        has_errors=True
                    )
                    return 0, 1, error_msg
            else:
                error_msg = f"Неизвестный провайдер: {provider}"
                logger.error(f"❌ {error_msg} для ресурса {resource.id}")
                self._create_error_news(resource, error_msg)
                return 0, 1, error_msg
        
        # Если ни один провайдер не сработал
        if not llm_response:
            if errors_chain:
                error_msg = f"Ошибка всех провайдеров: {llm_error}"
            else:
                error_msg = "Не настроен ни один провайдер LLM (Grok, Anthropic или OpenAI)"
            logger.error(f"❌ {error_msg} для ресурса {resource.id}")
            self._create_error_news(resource, error_msg)
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
                'main': """Найди на сайте {url} ({name}) все новости за период с {start_date} по {end_date} включительно.

Используй веб-поиск для поиска новостей. Ищи все статьи, публикации, пресс-релизы, новости, опубликованные на сайте за указанный период. Для каждой найденной новости найди заголовок, текст новости (1-2 абзаца) и ссылку на источник.""",
                'period': "Период поиска: с {start_date} по {end_date} включительно.",
                'json_format': """Верни ответ СТРОГО в формате JSON (только JSON, без дополнительного текста):

{{
  "news": [
    {{
      "title": "Заголовок новости на русском",
      "summary": "Текст новости на русском языке (1-2 абзаца). Пиши новость напрямую, как журналист, от третьего лица.",
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

Если новостей нет, верни: {{"news": []}}

Верни ТОЛЬКО JSON, без дополнительных комментариев или объяснений."""
            },
            'en': {
                'main': """Find all news on the website {url} ({name}) for the period from {start_date} to {end_date} inclusive.

Use web search to find news. Look for all articles, publications, press releases, news published on the website for the specified period. For each found news item, find the title, news text (1-2 paragraphs) and source link.""",
                'period': "Search period: from {start_date} to {end_date} inclusive.",
                'json_format': """Return the answer STRICTLY in JSON format (JSON only, without additional text):

{{
  "news": [
    {{
      "title": {{
        "en": "News title in English",
        "ru": "Заголовок новости на русском"
      }},
      "summary": {{
        "en": "News text in English (1-2 paragraphs). Write the news directly, as a journalist, in third person.",
        "ru": "Текст новости на русском языке (1-2 абзаца). Пиши новость напрямую, как журналист, от третьего лица."
      }},
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

If no news found, return: {{"news": []}}

Return ONLY JSON, without additional comments or explanations."""
            },
            'es': {
                'main': """Encuentra todas las noticias en el sitio web {url} ({name}) para el período del {start_date} al {end_date} inclusive.

Usa la búsqueda web para encontrar noticias. Busca todos los artículos, publicaciones, comunicados de prensa, noticias publicadas en el sitio web para el período especificado. Para cada noticia encontrada, encuentra el título, texto de la noticia (1-2 párrafos) y enlace a la fuente.""",
                'period': "Período de búsqueda: del {start_date} al {end_date} inclusive.",
                'json_format': """Devuelve la respuesta ESTRICTAMENTE en formato JSON (solo JSON, sin texto adicional):

{{
  "news": [
    {{
      "title": {{
        "es": "Título de la noticia en español",
        "ru": "Заголовок новости на русском"
      }},
      "summary": {{
        "es": "Texto de la noticia en español (1-2 párrafos). Escribe la noticia directamente, como periodista, en tercera persona.",
        "ru": "Текст новости на русском языке (1-2 абзаца). Пиши новость напрямую, как журналист, от третьего лица."
      }},
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

Si no se encuentran noticias, devuelve: {{"news": []}}

Devuelve SOLO JSON, sin comentarios adicionales o explicaciones."""
            },
            'de': {
                'main': """Finde alle Nachrichten auf der Website {url} ({name}) für den Zeitraum vom {start_date} bis {end_date} einschließlich.

Verwende die Websuche, um Nachrichten zu finden. Suche nach allen Artikeln, Veröffentlichungen, Pressemitteilungen, Nachrichten, die auf der Website für den angegebenen Zeitraum veröffentlicht wurden. Für jede gefundene Nachricht finde den Titel, den Nachrichtentext (1-2 Absätze) und den Quelllink.""",
                'period': "Suchzeitraum: vom {start_date} bis {end_date} einschließlich.",
                'json_format': """Gib die Antwort STRENG im JSON-Format zurück (nur JSON, ohne zusätzlichen Text):

{{
  "news": [
    {{
      "title": {{
        "de": "Nachrichtentitel auf Deutsch",
        "ru": "Заголовок новости на русском"
      }},
      "summary": {{
        "de": "Nachrichtentext auf Deutsch (1-2 Absätze). Schreibe die Nachricht direkt, als Journalist, in der dritten Person.",
        "ru": "Текст новости на русском языке (1-2 абзаца). Пиши новость напрямую, как журналист, от третьего лица."
      }},
      "source_url": "https://example.com/news/article"
    }}
  ]
}}

Wenn keine Nachrichten gefunden wurden, gib zurück: {{"news": []}}

Gib NUR JSON zurück, ohne zusätzliche Kommentare oder Erklärungen."""
            },
            'pt': {
                'main': """Encontre todas as notícias no site {url} ({name}) para o período de {start_date} a {end_date} inclusive.

Use a pesquisa na web para encontrar notícias. Procure por todos os artigos, publicações, comunicados de imprensa, notícias publicadas no site para o período especificado. Para cada notícia encontrada, encontre o título, texto da notícia (1-2 parágrafos) e link da fonte.""",
                'period': "Período de pesquisa: de {start_date} a {end_date} inclusive.",
                'json_format': """Retorne a resposta ESTRITAMENTE em formato JSON (apenas JSON, sem texto adicional):

{{
  "news": [
    {{
      "title": {{
        "pt": "Título da notícia em português",
        "ru": "Заголовок новости на русском"
      }},
      "summary": {{
        "pt": "Texto da notícia em português (1-2 parágrafos). Escreva a notícia diretamente, como jornalista, na terceira pessoa.",
        "ru": "Текст новости на русском языке (1-2 абзаца). Пиши новость напрямую, как журналист, от третьего лица."
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
        
        # Извлекаем домен из URL для использования в поиске site:
        domain = self._extract_domain(resource.url)
        
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
        # Используем domain для поиска site:, но оставляем полный url в описании
        return f"""{templates['main'].format(
            url=resource.url,
            domain=domain,
            name=resource.name,
            start_date=start_date_str,
            end_date=end_date_str
        )}
{templates['json_format']}"""

    def _query_openai(self, prompt: str) -> Optional[Dict]:
        """
        Запрос к OpenAI API с веб-поиском через Responses API.
        Отслеживает токены и стоимость.
        """
        if not self.openai_api_key:
            raise ValueError("OpenAI API key is not set")
        
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0
        
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.openai_api_key)
            result = None
            
            try:
                # Пробуем использовать Responses API для веб-поиска
                response = client.responses.create(
                    model=self.openai_model,
                    input=prompt,
                    tools=[{"type": "web_search"}],
                    temperature=self.temperature,
                )
                
                # Извлекаем метрики токенов (если доступны)
                if hasattr(response, 'usage'):
                    input_tokens = getattr(response.usage, 'input_tokens', 0) or 0
                    output_tokens = getattr(response.usage, 'output_tokens', 0) or 0
                
                content = response.output_text.strip()
                logger.info("OpenAI использовал Responses API с веб-поиском")
                
                try:
                    result = json.loads(content)
                except json.JSONDecodeError:
                    json_match = re.search(r'\{[^{}]*"news"[^{}]*\[.*?\]\s*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group(0))
                        except json.JSONDecodeError:
                            pass
                    
                    if not result:
                        logger.warning(f"OpenAI Responses API вернул текст вместо JSON: {content[:200]}")
                        result = {"news": []}
                
            except AttributeError:
                # Если Responses API недоступен
                logger.warning("Responses API недоступен, используем Chat Completions API")
                response = client.chat.completions.create(
                    model=self.openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты - эксперт по поиску новостей. Возвращай ответ в формате JSON."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    timeout=self.timeout
                )
                
                if response.usage:
                    input_tokens = response.usage.prompt_tokens or 0
                    output_tokens = response.usage.completion_tokens or 0
                
                content = response.choices[0].message.content.strip()
                result = json.loads(content)
            
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"OpenAI: {input_tokens} in, {output_tokens} out, {duration_ms}ms")
            
            # Трекинг API вызова
            news_count = len(result.get('news', [])) if result else 0
            self._track_api_call(
                provider='openai',
                model=self.openai_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=True,
                news_extracted=news_count
            )
            
            return result
            
        except ImportError:
            raise ImportError("OpenAI library is not installed. Install it with: pip install openai")
        except json.JSONDecodeError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._track_api_call(
                provider='openai',
                model=self.openai_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=False,
                error_message=f"Invalid JSON: {str(e)}"
            )
            logger.error(f"OpenAI returned invalid JSON: {str(e)}")
            raise ValueError(f"Invalid JSON response from OpenAI: {str(e)}")
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._track_api_call(
                provider='openai',
                model=self.openai_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=False,
                error_message=str(e)
            )
            logger.error(f"OpenAI API error: {str(e)}")
            raise
    
    def _query_grok(self, prompt: str, domain: str = None) -> Optional[Dict]:
        """
        Запрос к Grok (xAI) API с веб-поиском.
        Использует OpenAI-совместимый API xAI с инструментом web_search.
        Отслеживает токены и стоимость.
        
        Args:
            prompt: Текст промпта
            domain: Домен для ограничения поиска (опционально)
        """
        if not self.grok_api_key:
            raise ValueError("Grok API key is not set")
        
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0
        
        try:
            from openai import OpenAI
            
            # xAI предоставляет OpenAI-совместимый API
            client = OpenAI(
                api_key=self.grok_api_key,
                base_url="https://api.x.ai/v1",
            )
            
            # Настройки веб-поиска из конфигурации
            web_search_config = {
                "max_search_results": self.max_search_results,
                "search_context_size": self.search_context_size,
            }
            
            # Если передан домен, ограничиваем поиск только этим доменом
            if domain:
                web_search_config["allowed_domains"] = [domain]
            
            # Запрос к Grok с веб-поиском
            response = None
            try:
                response = client.chat.completions.create(
                    model=self.grok_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Используй веб-поиск для поиска новостей. Возвращай ответ в формате JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    web_search_options=web_search_config,
                    timeout=self.timeout
                )
            except TypeError:
                # Если web_search_options не поддерживается
                logger.warning("web_search_options не поддерживается, пробуем без него")
                try:
                    response = client.chat.completions.create(
                        model=self.grok_model,
                        messages=[
                            {
                                "role": "system",
                                "content": "Используй веб-поиск для поиска новостей. Возвращай ответ в формате JSON."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=self.temperature,
                        response_format={"type": "json_object"},
                        timeout=self.timeout
                    )
                except Exception as e:
                    logger.warning(f"Grok request with response_format failed: {str(e)}, trying without it")
                    response = client.chat.completions.create(
                        model=self.grok_model,
                        messages=[
                            {
                                "role": "system",
                                "content": "Используй веб-поиск для поиска новостей. Возвращай ответ в формате JSON."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=self.temperature,
                        timeout=self.timeout
                    )
            except Exception as e:
                logger.warning(f"Grok request with web_search_options failed: {str(e)}, trying without it")
                response = client.chat.completions.create(
                    model=self.grok_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Используй веб-поиск для поиска новостей. Возвращай ответ в формате JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=self.temperature,
                    timeout=self.timeout
                )
            
            # Извлекаем метрики токенов
            if response and response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
            
            # Извлекаем контент
            content = response.choices[0].message.content.strip()
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"Grok: {input_tokens} in, {output_tokens} out, {duration_ms}ms")
            logger.info(f"Grok raw output (первые 1000 символов): {content[:1000]}")
            
            # Парсим JSON из ответа
            result = None
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Ищем JSON блок в тексте
                json_match = re.search(r'\{[^{}]*"news"[^{}]*\[.*?\]\s*\}', content, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass
                
                # Пробуем найти JSON в markdown блоке
                if not result:
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group(1))
                        except json.JSONDecodeError:
                            pass
                
                if not result:
                    logger.warning(f"Grok вернул текст вместо JSON: {content[:200]}")
                    result = {"news": []}
            
            # Трекинг API вызова
            news_count = len(result.get('news', [])) if result else 0
            self._track_api_call(
                provider='grok',
                model=self.grok_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=True,
                news_extracted=news_count
            )
            
            return result
            
        except ImportError:
            raise ImportError("OpenAI library is not installed. Install it with: pip install openai")
        except json.JSONDecodeError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._track_api_call(
                provider='grok',
                model=self.grok_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=False,
                error_message=f"Invalid JSON: {str(e)}"
            )
            logger.error(f"Grok returned invalid JSON: {str(e)}")
            raise ValueError(f"Invalid JSON response from Grok: {str(e)}")
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._track_api_call(
                provider='grok',
                model=self.grok_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=False,
                error_message=str(e)
            )
            logger.error(f"Grok API error: {str(e)}")
            raise
    
    def _query_anthropic(self, prompt: str) -> Optional[Dict]:
        """
        Запрос к Anthropic (Claude) API с веб-поиском.
        Использует Claude Haiku 4.5 с инструментом web_search.
        Отслеживает токены и стоимость.
        """
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key is not set")
        
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0
        
        try:
            from anthropic import Anthropic
            
            client = Anthropic(api_key=self.anthropic_api_key)
            
            # Извлекаем домен из промпта для ограничения поиска
            url_match = re.search(r'https?://([^/\s]+)', prompt)
            domain = None
            if url_match:
                domain = url_match.group(1).replace('www.', '')
            
            # Формируем промпт для Anthropic
            if domain:
                anthropic_prompt = f"""Используй веб-поиск для поиска новостей на сайте {domain}.

{prompt}

ФОРМАТ ОТВЕТА:
Верни ответ ТОЛЬКО в формате JSON, БЕЗ объяснений.
Формат: {{"news": [{{"source_url": "...", "title": {{"ru": "...", "en": "..."}}, "summary": {{"ru": "...", "en": "..."}}}}, ...]}}"""
            else:
                anthropic_prompt = prompt
            
            # Параметры для веб-поиска
            web_search_tool = {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": self.max_search_results,
            }
            
            if domain:
                web_search_tool["allowed_domains"] = [domain]
            
            system_message = "Ты - помощник для поиска новостей. Верни результат ТОЛЬКО в формате JSON."
            
            response = client.messages.create(
                model=self.anthropic_model,
                max_tokens=6144,
                system=system_message,
                messages=[{"role": "user", "content": anthropic_prompt}],
                tools=[web_search_tool],
                temperature=self.temperature,
                timeout=self.timeout
            )
            
            # Извлекаем метрики токенов
            if hasattr(response, 'usage'):
                input_tokens = getattr(response.usage, 'input_tokens', 0) or 0
                output_tokens = getattr(response.usage, 'output_tokens', 0) or 0
            
            # Извлекаем контент
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text
            content = content.strip()
            
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Anthropic: {input_tokens} in, {output_tokens} out, {duration_ms}ms")
            
            # Парсим JSON
            result = None
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Ищем JSON в markdown блоке
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass
                
                if not result:
                    json_match = re.search(r'\{\s*"news"\s*:\s*\[.*?\]\s*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group(0))
                        except json.JSONDecodeError:
                            pass
                
                if not result:
                    # Рекурсивный поиск
                    brace_count = 0
                    start_idx = -1
                    for i, char in enumerate(content):
                        if char == '{':
                            if start_idx == -1:
                                start_idx = i
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0 and start_idx != -1:
                                try:
                                    parsed = json.loads(content[start_idx:i+1])
                                    if 'news' in parsed:
                                        result = parsed
                                        break
                                except json.JSONDecodeError:
                                    pass
                                start_idx = -1
                
                if not result:
                    logger.warning(f"Anthropic вернул текст вместо JSON: {content[:500]}")
                    result = {"news": []}
            
            # Трекинг API вызова
            news_count = len(result.get('news', [])) if result else 0
            self._track_api_call(
                provider='anthropic',
                model=self.anthropic_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=True,
                news_extracted=news_count
            )
            
            return result
            
        except ImportError:
            raise ImportError("Anthropic library is not installed. Install it with: pip install anthropic")
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._track_api_call(
                provider='anthropic',
                model=self.anthropic_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=False,
                error_message=str(e)
            )
            logger.error(f"Anthropic API error: {str(e)}")
            raise
    
    def _query_gemini(self, prompt: str) -> Optional[Dict]:
        """
        Запрос к Google Gemini API.
        Отслеживает токены и стоимость.
        """
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is not set")
        
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.gemini_api_key)
            
            try:
                model = genai.GenerativeModel(self.gemini_model)
                logger.info(f"Using Gemini model {self.gemini_model}")
            except Exception as e:
                logger.warning(f"Error initializing Gemini model {self.gemini_model}: {str(e)}")
                raise
            
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": self.temperature,
                    "response_mime_type": "application/json",
                }
            )
            
            # Извлекаем метрики токенов (если доступны)
            if hasattr(response, 'usage_metadata'):
                input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
                output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
            
            content = response.text.strip()
            # Убираем возможные markdown обертки
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            result = json.loads(content)
            
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Gemini: {input_tokens} in, {output_tokens} out, {duration_ms}ms")
            
            # Трекинг API вызова
            news_count = len(result.get('news', [])) if result else 0
            self._track_api_call(
                provider='gemini',
                model=self.gemini_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=True,
                news_extracted=news_count
            )
            
            return result
            
        except ImportError:
            raise ImportError("Google Generative AI library is not installed. Install it with: pip install google-generativeai")
        except json.JSONDecodeError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._track_api_call(
                provider='gemini',
                model=self.gemini_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=False,
                error_message=f"Invalid JSON: {str(e)}"
            )
            logger.error(f"Gemini returned invalid JSON: {str(e)}")
            raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._track_api_call(
                provider='gemini',
                model=self.gemini_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=False,
                error_message=str(e)
            )
            logger.error(f"Gemini API error: {str(e)}")
            raise
    
    # Методы _merge_and_summarize и _build_merge_prompt удалены - больше не нужны, так как используем только OpenAI
    
    def _create_news_post(self, news_item: Dict, resource: NewsResource):
        """Создает новость из данных, полученных от LLM"""
        # Извлекаем данные
        title_data = news_item.get('title', {})
        summary_data = news_item.get('summary', {})
        source_url = news_item.get('source_url', '')
        
        # Определяем язык источника
        source_language = getattr(resource, 'language', 'en') or 'en'
        
        # Обрабатываем разные форматы ответа:
        # - Для русских источников: title/summary — строки
        # - Для остальных: title/summary — объекты с языками
        if isinstance(title_data, str):
            # Русский источник — title/summary уже строки
            title_ru = title_data or 'Без заголовка'
            summary_ru = summary_data if isinstance(summary_data, str) else ''
            title_source = title_ru
            summary_source = summary_ru
        else:
            # Не-русский источник — извлекаем оба языка
            title_ru = title_data.get('ru', 'Без заголовка')
            summary_ru = summary_data.get('ru', '') if isinstance(summary_data, dict) else ''
            title_source = title_data.get(source_language, title_ru)
            summary_source = summary_data.get(source_language, summary_ru) if isinstance(summary_data, dict) else summary_ru
        
        # Если source_url из LLM пустой, используем URL ресурса
        if not source_url and resource:
            source_url = resource.url
        
        # Используем summary напрямую без дополнительной информации об источнике
        body_ru = summary_ru
        
        # Создаем новость
        news_post = NewsPost.objects.create(
            title=title_ru,
            body=body_ru,
            source_url=source_url or '',  # Всегда сохраняем URL источника
            status='draft',
            source_language=source_language,
            author=self.user,
            pub_date=timezone.now()
        )
        
        # Сохраняем оригинальный язык источника если он отличается от русского
        if source_language != 'ru' and title_source:
            setattr(news_post, f'title_{source_language}', title_source)
        if source_language != 'ru' and summary_source:
            setattr(news_post, f'body_{source_language}', summary_source)
        
        news_post.save()
        logger.info(f"Created news post: {news_post.id} - {title_ru}")
    
    def _create_no_news_news(self, resource: NewsResource, start_date: date, end_date: date):
        """Создает новость о том, что новостей не найдено"""
        title_ru = f"Новостей от источника '{resource.name}' не найдено"
        title_en = f"No news found from source '{resource.name}'"
        title_de = f"Keine Nachrichten von Quelle '{resource.name}' gefunden"
        title_pt = f"Nenhuma notícia encontrada da fonte '{resource.name}'"
        
        body_ru = f"За период с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')} на ресурсе [{resource.name}]({resource.url}) новостей не обнаружено."
        body_en = f"For the period from {start_date.strftime('%d.%m.%Y')} to {end_date.strftime('%d.%m.%Y')}, no news was found on the resource [{resource.name}]({resource.url})."
        body_de = f"Für den Zeitraum vom {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')} wurden auf der Ressource [{resource.name}]({resource.url}) keine Nachrichten gefunden."
        body_pt = f"No período de {start_date.strftime('%d.%m.%Y')} a {end_date.strftime('%d.%m.%Y')}, nenhuma notícia foi encontrada no recurso [{resource.name}]({resource.url})."
        
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
        
        body_ru = f"При попытке получить новости с ресурса [{resource.name}]({resource.url}) произошла ошибка:\n\n{error_message}"
        body_en = f"An error occurred while trying to get news from resource [{resource.name}]({resource.url}):\n\n{error_message}"
        body_de = f"Beim Versuch, Nachrichten von der Ressource [{resource.name}]({resource.url}) zu erhalten, ist ein Fehler aufgetreten:\n\n{error_message}"
        body_pt = f"Ocorreu um erro ao tentar obter notícias do recurso [{resource.name}]({resource.url}):\n\n{error_message}"
        
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
                    # Используем провайдер из status_obj, если указан, иначе 'auto'
                    provider = status_obj.provider if status_obj else 'auto'
                    created, errors, error_msg = self.discover_news_for_resource(resource, provider=provider)
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
    
    def discover_news_for_manufacturer(self, manufacturer: Manufacturer, provider: str = 'auto') -> Tuple[int, int, Optional[str]]:
        """
        Ищет новости о производителе в интернете.
        
        Args:
            manufacturer: Производитель
            provider: Провайдер LLM ('auto', 'grok', 'anthropic', 'openai')
            
        Returns:
            Tuple[created_count, error_count, error_message]
        """
        # Получаем период поиска
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        
        # Формируем промпт для LLM
        prompt = self._build_manufacturer_search_prompt(manufacturer, last_search_date, today)
        
        # Получаем ответ от LLM (с учетом выбранного провайдера)
        llm_response = None
        llm_error = None
        provider_used = None
        errors_chain = []
        
        # Если provider='auto' - используем цепочку провайдеров
        if provider == 'auto':
            # Пробуем сначала Grok, если включен
            if self.use_grok and self.grok_api_key:
                try:
                    logger.info(f"[Grok] Начинаю обработку производителя {manufacturer.id} ({manufacturer.name})")
                    llm_response = self._query_grok(prompt)
                    provider_used = 'Grok'
                    logger.info(f"[Grok] ✅ Успешно обработал производителя {manufacturer.id} ({manufacturer.name})")
                except Exception as e:
                    logger.warning(f"[Grok] ❌ Ошибка для производителя {manufacturer.id}: {str(e)}")
                    errors_chain.append(f"Grok: {str(e)}")
                    llm_error = "; ".join(errors_chain)
            
            # Если Grok не сработал, пробуем Anthropic (если включен)
            if not llm_response and self.use_anthropic and self.anthropic_api_key:
                try:
                    logger.info(f"[Anthropic] Пробую обработать производителя {manufacturer.id} ({manufacturer.name})")
                    llm_response = self._query_anthropic(prompt)
                    provider_used = 'Anthropic'
                    logger.info(f"[Anthropic] ✅ Успешно обработал производителя {manufacturer.id} ({manufacturer.name})")
                except Exception as e:
                    logger.warning(f"[Anthropic] ❌ Ошибка для производителя {manufacturer.id}: {str(e)}")
                    errors_chain.append(f"Anthropic: {str(e)}")
                    llm_error = "; ".join(errors_chain)
            
            # Если Grok и Anthropic не сработали, пробуем OpenAI как резервный
            if not llm_response and self.use_openai_fallback and self.openai_api_key:
                try:
                    logger.info(f"[OpenAI Fallback] Пробую обработать производителя {manufacturer.id} ({manufacturer.name})")
                    llm_response = self._query_openai(prompt)
                    provider_used = 'OpenAI (fallback)'
                    logger.info(f"[OpenAI Fallback] ✅ Успешно обработал производителя {manufacturer.id} ({manufacturer.name})")
                except Exception as e:
                    logger.error(f"[OpenAI Fallback] ❌ Ошибка для производителя {manufacturer.id}: {str(e)}")
                    errors_chain.append(f"OpenAI fallback: {str(e)}")
                    llm_error = "; ".join(errors_chain)
        else:
            # Используем конкретный провайдер (копируем логику из discover_news_for_resource)
            if provider == 'grok':
                if not self.grok_api_key:
                    error_msg = "Grok API key не настроен"
                    logger.error(f"❌ {error_msg} для производителя {manufacturer.id}")
                    self._create_error_manufacturer(manufacturer, error_msg)
                    return 0, 1, error_msg
                try:
                    logger.info(f"[Grok] Начинаю обработку производителя {manufacturer.id} ({manufacturer.name})")
                    llm_response = self._query_grok(prompt)
                    provider_used = 'Grok'
                    logger.info(f"[Grok] ✅ Успешно обработал производителя {manufacturer.id} ({manufacturer.name})")
                except Exception as e:
                    error_msg = f"Ошибка Grok: {str(e)}"
                    logger.error(f"❌ {error_msg} для производителя {manufacturer.id}")
                    self._create_error_manufacturer(manufacturer, error_msg)
                    self._update_manufacturer_statistics(
                        manufacturer=manufacturer,
                        news_count=0,
                        error_count=1,
                        is_no_news=False,
                        has_errors=True
                    )
                    return 0, 1, error_msg
            
            elif provider == 'anthropic':
                if not self.anthropic_api_key:
                    error_msg = "Anthropic API key не настроен"
                    logger.error(f"❌ {error_msg} для производителя {manufacturer.id}")
                    self._create_error_manufacturer(manufacturer, error_msg)
                    return 0, 1, error_msg
                try:
                    logger.info(f"[Anthropic] Начинаю обработку производителя {manufacturer.id} ({manufacturer.name})")
                    llm_response = self._query_anthropic(prompt)
                    provider_used = 'Anthropic'
                    logger.info(f"[Anthropic] ✅ Успешно обработал производителя {manufacturer.id} ({manufacturer.name})")
                except Exception as e:
                    error_msg = f"Ошибка Anthropic: {str(e)}"
                    logger.error(f"❌ {error_msg} для производителя {manufacturer.id}")
                    self._create_error_manufacturer(manufacturer, error_msg)
                    self._update_manufacturer_statistics(
                        manufacturer=manufacturer,
                        news_count=0,
                        error_count=1,
                        is_no_news=False,
                        has_errors=True
                    )
                    return 0, 1, error_msg
            
            elif provider == 'openai':
                if not self.openai_api_key:
                    error_msg = "OpenAI API key не настроен"
                    logger.error(f"❌ {error_msg} для производителя {manufacturer.id}")
                    self._create_error_manufacturer(manufacturer, error_msg)
                    return 0, 1, error_msg
                try:
                    logger.info(f"[OpenAI] Начинаю обработку производителя {manufacturer.id} ({manufacturer.name})")
                    llm_response = self._query_openai(prompt)
                    provider_used = 'OpenAI'
                    logger.info(f"[OpenAI] ✅ Успешно обработал производителя {manufacturer.id} ({manufacturer.name})")
                except Exception as e:
                    error_msg = f"Ошибка OpenAI: {str(e)}"
                    logger.error(f"❌ {error_msg} для производителя {manufacturer.id}")
                    self._create_error_manufacturer(manufacturer, error_msg)
                    self._update_manufacturer_statistics(
                        manufacturer=manufacturer,
                        news_count=0,
                        error_count=1,
                        is_no_news=False,
                        has_errors=True
                    )
                    return 0, 1, error_msg
            else:
                error_msg = f"Неизвестный провайдер: {provider}"
                logger.error(f"❌ {error_msg} для производителя {manufacturer.id}")
                self._create_error_manufacturer(manufacturer, error_msg)
                return 0, 1, error_msg
        
        # Если ни один провайдер не сработал
        if not llm_response:
            if errors_chain:
                error_msg = f"Ошибка всех провайдеров: {llm_error}"
            else:
                error_msg = "Не настроен ни один провайдер LLM (Grok, Anthropic или OpenAI)"
            logger.error(f"❌ {error_msg} для производителя {manufacturer.id}")
            self._create_error_manufacturer(manufacturer, error_msg)
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
            
            return f"""Find all news about manufacturer {manufacturer.name} for the period from {start_date_str} to {end_date_str} inclusive.

Use web search to find news. Look for all articles, publications, press releases, news about the manufacturer published on industry publications, news portals, press releases, or other sources for the specified period. For each found news item, find the title, news text (1-2 paragraphs) and source link.

{templates['json_format']}"""
        
        websites_str = ", ".join(websites)
        templates = self._get_prompt_templates('en')
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        # Извлекаем домены из URL для использования в поиске site:
        domains = [self._extract_domain(url) for url in websites]
        domains_str = ", ".join([f"site:{domain}" for domain in domains])
        
        return f"""Find all news about manufacturer {manufacturer.name} for the period from {start_date_str} to {end_date_str} inclusive.

Official manufacturer websites: {websites_str}

Use web search to find news. Look for all articles, publications, press releases, news about the manufacturer published on these websites or other industry sources for the specified period. For each found news item, find the title, news text (1-2 paragraphs) and source link.

{templates['json_format']}"""
    
    def _create_manufacturer_news_post(self, news_item: Dict, manufacturer: Manufacturer):
        """Создает новость о производителе из данных, полученных от LLM"""
        # Извлекаем данные
        title_data = news_item.get('title', {})
        summary_data = news_item.get('summary', {})
        source_url = news_item.get('source_url', '')
        
        # Для производителей всегда используем английский как язык источника
        source_language = 'en'
        
        # Обрабатываем разные форматы ответа
        if isinstance(title_data, str):
            title_ru = title_data or 'Без заголовка'
            summary_ru = summary_data if isinstance(summary_data, str) else ''
            title_en = title_ru
            summary_en = summary_ru
        else:
            title_ru = title_data.get('ru', 'Без заголовка')
            summary_ru = summary_data.get('ru', '') if isinstance(summary_data, dict) else ''
            title_en = title_data.get('en', title_ru)
            summary_en = summary_data.get('en', summary_ru) if isinstance(summary_data, dict) else summary_ru
        
        if not source_url:
            # Если source_url пустой, используем первый сайт производителя
            source_url = manufacturer.website_1 or ''
        
        # Используем summary напрямую без дополнительной информации об источнике
        body_ru = summary_ru
        
        # Создаем новость
        news_post = NewsPost.objects.create(
            title=title_ru,
            body=body_ru,
            source_url=source_url,
            manufacturer=manufacturer,  # Связываем с производителем
            status='draft',
            source_language=source_language,
            author=self.user,
            pub_date=timezone.now()
        )
        
        # Сохраняем английскую версию
        if title_en:
            setattr(news_post, 'title_en', title_en)
        if summary_en:
            setattr(news_post, 'body_en', summary_en)
        
        news_post.save()
        logger.info(f"Created news post for manufacturer {manufacturer.id}: {news_post.id} - {title_ru}")
    
    def _create_no_news_manufacturer(self, manufacturer: Manufacturer, start_date: date, end_date: date):
        """Создает новость о том, что новостей о производителе не найдено"""
        title_ru = f"Новостей о производителе '{manufacturer.name}' не найдено"
        title_en = f"No news found about manufacturer '{manufacturer.name}'"
        title_de = f"Keine Nachrichten über Hersteller '{manufacturer.name}' gefunden"
        title_pt = f"Nenhuma notícia encontrada sobre o fabricante '{manufacturer.name}'"
        
        source_url = manufacturer.website_1 or ''
        
        body_ru = f"За период с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')} новостей о производителе {manufacturer.name} не обнаружено."
        body_en = f"For the period from {start_date.strftime('%d.%m.%Y')} to {end_date.strftime('%d.%m.%Y')}, no news was found about manufacturer {manufacturer.name}."
        body_de = f"Für den Zeitraum vom {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')} wurden keine Nachrichten über Hersteller {manufacturer.name} gefunden."
        body_pt = f"No período de {start_date.strftime('%d.%m.%Y')} a {end_date.strftime('%d.%m.%Y')}, nenhuma notícia foi encontrada sobre o fabricante {manufacturer.name}."
        
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
        
        source_url = manufacturer.website_1 or ''
        
        body_ru = f"При попытке получить новости о производителе {manufacturer.name} произошла ошибка:\n\n{error_message}"
        body_en = f"An error occurred while trying to get news about manufacturer {manufacturer.name}:\n\n{error_message}"
        body_de = f"Beim Versuch, Nachrichten über Hersteller {manufacturer.name} zu erhalten, ist ein Fehler aufgetreten:\n\n{error_message}"
        body_pt = f"Ocorreu um erro ao tentar obter notícias sobre o fabricante {manufacturer.name}:\n\n{error_message}"
        
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
                    # Используем провайдер из status_obj, если указан, иначе 'auto'
                    provider = status_obj.provider if status_obj else 'auto'
                    created, errors, error_msg = self.discover_news_for_manufacturer(manufacturer, provider=provider)
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
