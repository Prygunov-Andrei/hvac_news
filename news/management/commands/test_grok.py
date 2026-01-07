"""
Management command для тестирования Grok на нескольких источниках.
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
    help = 'Тестирует Grok на указанном количестве источников'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=5,
            help='Количество источников для тестирования (по умолчанию: 5)'
        )
        parser.add_argument(
            '--start-date',
            type=str,
            default='2025-12-10',
            help='Дата начала поиска в формате YYYY-MM-DD (по умолчанию: 2025-12-10)'
        )
        parser.add_argument(
            '--start-id',
            type=int,
            help='ID источника, с которого начинать (если не указан, берется первый)'
        )

    def handle(self, *args, **options):
        count = options['count']
        start_date_str = options['start_date']
        start_id = options.get('start_id')
        
        # Парсим дату начала поиска
        try:
            start_date = date.fromisoformat(start_date_str)
        except ValueError:
            self.stdout.write(self.style.ERROR(f'Неверный формат даты: {start_date_str}. Используйте формат YYYY-MM-DD'))
            return
        
        # Устанавливаем дату начала поиска
        self.stdout.write(f'Устанавливаем дату начала поиска: {start_date}')
        NewsDiscoveryRun.update_last_search_date(start_date)
        
        # Получаем пользователя
        user = User.objects.filter(is_staff=True).first()
        if not user:
            self.stdout.write(self.style.ERROR('Не найден ни один администратор'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'Используется пользователь: {user.email}'))
        
        # Получаем источники для тестирования
        if start_id:
            resources = NewsResource.objects.filter(id__gte=start_id).order_by('id')[:count]
        else:
            resources = NewsResource.objects.all().order_by('id')[:count]
        
        total_count = resources.count()
        
        if total_count == 0:
            self.stdout.write(self.style.WARNING('Не найдено источников для тестирования'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\nТестируем Grok на {total_count} источниках:'))
        for i, resource in enumerate(resources, 1):
            self.stdout.write(f'  {i}. ID {resource.id} - {resource.name} ({resource.url})')
        
        # Создаем сервис
        service = NewsDiscoveryService(user=user)
        
        self.stdout.write(self.style.SUCCESS('\nНачинаем тестирование...'))
        self.stdout.write('=' * 80)
        
        total_created = 0
        total_errors = 0
        
        for i, resource in enumerate(resources, 1):
            self.stdout.write(f'\n[{i}/{total_count}] Обработка: ID {resource.id} - {resource.name}')
            self.stdout.write(f'  URL: {resource.url}')
            
            try:
                created, errors, error_msg = service.discover_news_for_resource(resource)
                total_created += created
                total_errors += errors
                
                if created > 0:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Создано новостей: {created}'))
                if errors > 0:
                    self.stdout.write(self.style.WARNING(f'  ⚠ Ошибок: {errors}'))
                if error_msg:
                    self.stdout.write(self.style.ERROR(f'  ✗ Ошибка: {error_msg}'))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Критическая ошибка: {str(e)}'))
                total_errors += 1
                logger.error(f"Error processing resource {resource.id}: {str(e)}", exc_info=True)
        
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('\nТестирование завершено!'))
        self.stdout.write(f'Создано новостей: {total_created}')
        self.stdout.write(f'Ошибок: {total_errors}')
        self.stdout.write(f'Обработано источников: {total_count}')
