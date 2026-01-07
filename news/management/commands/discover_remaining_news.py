"""
Management command для обработки оставшихся источников новостей.
Запускает поиск только для источников, которые еще не были обработаны.
"""
import logging
from datetime import date
from django.core.management.base import BaseCommand
from django.utils import timezone
from references.models import NewsResource
from news.discovery_service import NewsDiscoveryService
from news.models import NewsDiscoveryRun, NewsDiscoveryStatus
from users.models import User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Обрабатывает оставшиеся источники новостей, начиная с указанного ID'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-id',
            type=int,
            default=245,
            help='ID источника, с которого начинать обработку (по умолчанию: 245)'
        )
        parser.add_argument(
            '--start-date',
            type=str,
            default='2025-12-10',
            help='Дата начала поиска в формате YYYY-MM-DD (по умолчанию: 2025-12-10)'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='ID пользователя для создания новостей (если не указан, берется первый staff пользователь)'
        )

    def handle(self, *args, **options):
        start_id = options['start_id']
        start_date_str = options['start_date']
        user_id = options.get('user_id')
        
        # Парсим дату начала поиска
        try:
            start_date = date.fromisoformat(start_date_str)
        except ValueError:
            self.stdout.write(self.style.ERROR(f'Неверный формат даты: {start_date_str}. Используйте формат YYYY-MM-DD'))
            return
        
        # Получаем пользователя
        if user_id:
            try:
                user = User.objects.get(id=user_id, is_staff=True)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Пользователь с ID {user_id} не найден или не является администратором'))
                return
        else:
            # Берем первого staff пользователя
            user = User.objects.filter(is_staff=True).first()
            if not user:
                self.stdout.write(self.style.ERROR('Не найден ни один администратор. Создайте администратора или укажите --user-id'))
                return
        
        self.stdout.write(self.style.SUCCESS(f'Используется пользователь: {user.email}'))
        
        # Устанавливаем дату начала поиска
        self.stdout.write(f'Устанавливаем дату начала поиска: {start_date}')
        NewsDiscoveryRun.update_last_search_date(start_date)
        
        # Получаем список оставшихся источников
        remaining_resources = NewsResource.objects.filter(id__gte=start_id).order_by('id')
        total_count = remaining_resources.count()
        
        if total_count == 0:
            self.stdout.write(self.style.WARNING(f'Не найдено источников с ID >= {start_id}'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'Найдено источников для обработки: {total_count}'))
        self.stdout.write(f'Первый источник: ID {remaining_resources.first().id} - {remaining_resources.first().name}')
        self.stdout.write(f'Последний источник: ID {remaining_resources.last().id} - {remaining_resources.last().name}')
        
        # Создаем статус для отслеживания прогресса
        status_obj = NewsDiscoveryStatus.create_new_status(total_count, search_type='resources')
        
        # Создаем сервис и запускаем обработку
        service = NewsDiscoveryService(user=user)
        
        self.stdout.write(self.style.SUCCESS('\nНачинаем обработку...'))
        self.stdout.write('=' * 80)
        
        try:
            # Модифицируем discover_all_news для работы с конкретным списком источников
            stats = self._discover_remaining_news(service, list(remaining_resources), status_obj)
            
            self.stdout.write('=' * 80)
            self.stdout.write(self.style.SUCCESS('\nОбработка завершена!'))
            self.stdout.write(f'Создано новостей: {stats["created"]}')
            self.stdout.write(f'Ошибок: {stats["errors"]}')
            self.stdout.write(f'Обработано источников: {stats["total_processed"]}')
            
            # Обновляем дату последнего поиска на сегодня
            NewsDiscoveryRun.update_last_search_date(timezone.now().date())
            self.stdout.write(f'\nДата последнего поиска обновлена на: {timezone.now().date()}')
            
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n\nОбработка прервана пользователем'))
            if status_obj:
                status_obj.status = 'interrupted'
                status_obj.save()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n\nКритическая ошибка: {str(e)}'))
            logger.error(f"Critical error in discover_remaining_news: {str(e)}", exc_info=True)
            if status_obj:
                status_obj.status = 'error'
                status_obj.save()
            raise
    
    def _discover_remaining_news(self, service: NewsDiscoveryService, resources: list, status_obj: NewsDiscoveryStatus) -> dict:
        """
        Обрабатывает список источников с отслеживанием прогресса.
        Адаптированная версия discover_all_news для работы с конкретным списком.
        """
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
                
                # Выводим прогресс в консоль
                progress_percent = int((processed_count / status_obj.total_count) * 100) if status_obj.total_count > 0 else 0
                self.stdout.write(f'\n[{processed_count}/{status_obj.total_count}] ({progress_percent}%) Обработка: ID {resource.id} - {resource.name}')
                
                # Обновляем прогресс
                if status_obj:
                    status_obj.processed_count = processed_count
                    status_obj.save()
                
                try:
                    created, errors, error_msg = service.discover_news_for_resource(resource)
                    total_created += created
                    total_errors += errors
                    
                    if created > 0:
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Создано новостей: {created}'))
                    if errors > 0:
                        self.stdout.write(self.style.WARNING(f'  ⚠ Ошибок: {errors}'))
                    
                    if error_msg and resource not in retry_queue:
                        # Если была ошибка API - добавляем в очередь для повтора
                        retry_queue.append(resource)
                        logger.info(f"Resource {resource.id} added to retry queue due to API error")
                    
                except Exception as e:
                    logger.error(f"Unexpected error processing resource {resource.id}: {str(e)}")
                    self.stdout.write(self.style.ERROR(f'  ✗ Критическая ошибка: {str(e)}'))
                    total_errors += 1
                    if resource not in retry_queue:
                        retry_queue.append(resource)
            
            # Обновляем статус на завершенный
            if status_obj:
                status_obj.status = 'completed'
                status_obj.save()
        
        except Exception as e:
            logger.error(f"Critical error in _discover_remaining_news: {str(e)}")
            if status_obj:
                status_obj.status = 'error'
                status_obj.save()
            raise
        
        return {
            'created': total_created,
            'errors': total_errors,
            'total_processed': processed_count
        }
