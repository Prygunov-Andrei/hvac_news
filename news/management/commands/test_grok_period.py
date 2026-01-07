"""
Тестовый скрипт для проверки Grok на конкретном периоде.
"""
import logging
from datetime import date
from django.core.management.base import BaseCommand
from django.utils import timezone
from references.models import NewsResource
from news.discovery_service import NewsDiscoveryService
from news.models import NewsDiscoveryRun
from users.models import User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Тестирует Grok на указанном периоде'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            default='2025-11-25',
            help='Дата начала поиска в формате YYYY-MM-DD'
        )
        parser.add_argument(
            '--end-date',
            type=str,
            default='2025-12-10',
            help='Дата окончания поиска в формате YYYY-MM-DD'
        )
        parser.add_argument(
            '--count',
            type=int,
            default=5,
            help='Количество источников для тестирования'
        )
        parser.add_argument(
            '--start-id',
            type=int,
            default=198,
            help='ID источника, с которого начинать'
        )

    def handle(self, *args, **options):
        start_date_str = options['start_date']
        end_date_str = options['end_date']
        count = options['count']
        start_id = options['start_id']
        
        # Парсим даты
        try:
            start_date = date.fromisoformat(start_date_str)
            end_date = date.fromisoformat(end_date_str)
        except ValueError:
            self.stdout.write(self.style.ERROR(f'Неверный формат даты. Используйте формат YYYY-MM-DD'))
            return
        
        if start_date >= end_date:
            self.stdout.write(self.style.ERROR(f'Дата начала должна быть раньше даты окончания'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\n📅 Период поиска:'))
        self.stdout.write(f'   Начало: {start_date.strftime("%d.%m.%Y")} (включительно)')
        self.stdout.write(f'   Конец: {end_date.strftime("%d.%m.%Y")} (включительно)')
        
        # Сохраняем текущую дату последнего поиска
        original_last_search = NewsDiscoveryRun.get_last_search_date()
        
        # Временно устанавливаем дату начала поиска
        NewsDiscoveryRun.update_last_search_date(start_date)
        
        # Получаем пользователя
        user = User.objects.filter(is_staff=True).first()
        if not user:
            self.stdout.write(self.style.ERROR('Не найден ни один администратор'))
            return
        
        # Получаем источники
        resources = NewsResource.objects.filter(id__gte=start_id).order_by('id')[:count]
        total_count = resources.count()
        
        if total_count == 0:
            self.stdout.write(self.style.WARNING('Не найдено источников для тестирования'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\nТестируем Grok на {total_count} источниках:'))
        for i, resource in enumerate(resources, 1):
            self.stdout.write(f'  {i}. ID {resource.id} - {resource.name}')
        
        # Создаем сервис с переопределением периода
        service = NewsDiscoveryService(user=user)
        
        # Переопределяем метод для использования фиксированной конечной даты
        original_discover = service.discover_news_for_resource
        
        def discover_with_fixed_period(resource):
            """Обертка для использования фиксированного периода"""
            from news.models import NewsDiscoveryRun
            from django.utils import timezone
            
            # Временно переопределяем get_last_search_date и today
            original_get_last = NewsDiscoveryRun.get_last_search_date
            original_today = timezone.now().date
            
            # Мокаем функции для использования фиксированных дат
            NewsDiscoveryRun.get_last_search_date = lambda: start_date
            timezone.now = lambda: type('MockTime', (), {
                'date': lambda: end_date,
                'now': lambda: timezone.datetime.now()
            })()
            
            try:
                result = original_discover(resource)
            finally:
                # Восстанавливаем оригинальные функции
                NewsDiscoveryRun.get_last_search_date = original_get_last
                timezone.now = original_today
            
            return result
        
        service.discover_news_for_resource = discover_with_fixed_period
        
        self.stdout.write(self.style.SUCCESS('\nНачинаем тестирование...'))
        self.stdout.write('=' * 80)
        
        total_created = 0
        total_errors = 0
        found_news_count = 0
        
        for i, resource in enumerate(resources, 1):
            self.stdout.write(f'\n[{i}/{total_count}] Обработка: ID {resource.id} - {resource.name}')
            
            try:
                # Вручную формируем промпт с фиксированными датами
                prompt = service._build_search_prompt(resource, start_date, end_date)
                
                # Вызываем Grok напрямую
                try:
                    llm_response = service._query_grok(prompt)
                    provider = 'Grok'
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  ⚠️  Grok ошибка: {str(e)}'))
                    if service.use_openai_fallback:
                        llm_response = service._query_openai(prompt)
                        provider = 'OpenAI (fallback)'
                    else:
                        raise
                
                self.stdout.write(self.style.SUCCESS(f'  ✓ Использован провайдер: {provider}'))
                
                # Обрабатываем ответ
                final_news = []
                if isinstance(llm_response, dict) and 'news' in llm_response:
                    final_news = llm_response['news']
                
                if not final_news or len(final_news) == 0:
                    service._create_no_news_news(resource, start_date, end_date)
                    total_created += 1
                    self.stdout.write(self.style.WARNING(f'  ⚠️  Новостей не найдено'))
                else:
                    for news_item in final_news:
                        try:
                            service._create_news_post(news_item, resource)
                            total_created += 1
                            found_news_count += 1
                        except Exception as e:
                            logger.error(f"Error creating news post: {str(e)}")
                            total_errors += 1
                    
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Найдено новостей: {len(final_news)}'))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Критическая ошибка: {str(e)}'))
                total_errors += 1
                logger.error(f"Error processing resource {resource.id}: {str(e)}", exc_info=True)
        
        # Восстанавливаем оригинальную дату
        NewsDiscoveryRun.update_last_search_date(original_last_search)
        
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('\nТестирование завершено!'))
        self.stdout.write(f'Создано записей: {total_created}')
        self.stdout.write(f'Найдено реальных новостей: {found_news_count}')
        self.stdout.write(f'Ошибок: {total_errors}')
        self.stdout.write(f'Обработано источников: {total_count}')
