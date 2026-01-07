"""
Management команда для тестирования поиска новостей.
Тестирует один ресурс через API.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
from references.models import NewsResource
from news.discovery_service import NewsDiscoveryService
from news.models import NewsDiscoveryRun
from users.models import User


class Command(BaseCommand):
    help = 'Тестирует поиск новостей для одного ресурса'

    def add_arguments(self, parser):
        parser.add_argument(
            '--resource-id',
            type=int,
            help='ID ресурса для тестирования (если не указан, берется первый)',
        )
        parser.add_argument(
            '--set-date',
            type=str,
            help='Установить дату последнего поиска (формат: YYYY-MM-DD)',
        )

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("ТЕСТИРОВАНИЕ ПОИСКА НОВОСТЕЙ"))
        self.stdout.write("=" * 60)
        
        # Получаем ресурс для тестирования
        if options['resource_id']:
            try:
                resource = NewsResource.objects.get(id=options['resource_id'])
            except NewsResource.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Ресурс с ID {options['resource_id']} не найден!"))
                return
        else:
            resource = NewsResource.objects.first()
            if not resource:
                self.stdout.write(self.style.ERROR("В базе данных нет источников новостей!"))
                return
        
        self.stdout.write(f"\nВыбран ресурс для тестирования:")
        self.stdout.write(f"  ID: {resource.id}")
        self.stdout.write(f"  Название: {resource.name}")
        self.stdout.write(f"  URL: {resource.url}")
        self.stdout.write(f"  Раздел: {resource.section or 'Не указан'}")
        
        # Получаем администратора
        test_user = User.objects.filter(is_superuser=True).first()
        if not test_user:
            self.stdout.write(self.style.ERROR("\nНе найден администратор для тестирования!"))
            return
        
        self.stdout.write(f"\nПользователь: {test_user.email}")
        
        # Получаем период поиска
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        
        self.stdout.write(f"\nПериод поиска:")
        self.stdout.write(f"  С: {last_search_date.strftime('%d.%m.%Y')}")
        self.stdout.write(f"  По: {today.strftime('%d.%m.%Y')}")
        
        # Создаем сервис
        self.stdout.write(f"\nСоздание сервиса поиска...")
        service = NewsDiscoveryService(user=test_user)
        
        self.stdout.write(f"  OpenAI модель: {service.openai_model}")
        self.stdout.write(f"  Gemini модель: {service.gemini_model}")
        self.stdout.write(f"  Таймаут: {service.timeout} секунд")
        
        # Проверяем наличие API ключей
        if not service.openai_api_key:
            self.stdout.write(self.style.WARNING("\nПРЕДУПРЕЖДЕНИЕ: OpenAI API ключ не установлен!"))
        else:
            masked_key = '*' * 20 + '...' + service.openai_api_key[-4:] if len(service.openai_api_key) > 4 else '***'
            self.stdout.write(f"  OpenAI API ключ: {masked_key}")
        
        if not service.gemini_api_key:
            self.stdout.write(self.style.WARNING("\nПРЕДУПРЕЖДЕНИЕ: Gemini API ключ не установлен!"))
        else:
            masked_key = '*' * 20 + '...' + service.gemini_api_key[-4:] if len(service.gemini_api_key) > 4 else '***'
            self.stdout.write(f"  Gemini API ключ: {masked_key}")
        
        # Запускаем поиск для одного ресурса
        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS("ЗАПУСК ПОИСКА НОВОСТЕЙ"))
        self.stdout.write("=" * 60)
        
        # Получаем период поиска для формирования промпта
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        
        # Формируем промпт и тестируем API напрямую
        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS("ТЕСТИРОВАНИЕ API"))
        self.stdout.write("=" * 60)
        
        prompt = service._build_search_prompt(resource, last_search_date, today)
        self.stdout.write(f"\nПромпт (первые 500 символов):")
        self.stdout.write(prompt[:500] + "...")
        
        # Тестируем OpenAI
        self.stdout.write(f"\n\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS("ОТВЕТ OPENAI API"))
        self.stdout.write("=" * 60)
        openai_response = None
        try:
            openai_response = service._query_openai(prompt)
            import json
            self.stdout.write(f"\nСтатус: Успешно")
            self.stdout.write(f"\nОтвет (JSON):")
            self.stdout.write(json.dumps(openai_response, ensure_ascii=False, indent=2))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nОшибка: {str(e)}"))
        
        # Тестируем Gemini
        self.stdout.write(f"\n\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS("ОТВЕТ GEMINI API"))
        self.stdout.write("=" * 60)
        gemini_response = None
        try:
            gemini_response = service._query_gemini(prompt)
            import json
            self.stdout.write(f"\nСтатус: Успешно")
            self.stdout.write(f"\nОтвет (JSON):")
            self.stdout.write(json.dumps(gemini_response, ensure_ascii=False, indent=2))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nОшибка: {str(e)}"))
        
        # Теперь запускаем полный процесс поиска
        self.stdout.write(f"\n\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS("ПОЛНЫЙ ПРОЦЕСС ПОИСКА"))
        self.stdout.write("=" * 60)
        
        try:
            created_count, error_count, error_message = service.discover_news_for_resource(resource)
            
            self.stdout.write(f"\nРЕЗУЛЬТАТЫ:")
            self.stdout.write(self.style.SUCCESS(f"  Создано новостей: {created_count}"))
            if error_count > 0:
                self.stdout.write(self.style.ERROR(f"  Ошибок: {error_count}"))
            else:
                self.stdout.write(f"  Ошибок: {error_count}")
            
            if error_message:
                self.stdout.write(self.style.WARNING(f"  Сообщение об ошибке: {error_message}"))
            
            # Проверяем созданные новости
            from news.models import NewsPost
            recent_news = NewsPost.objects.filter(
                source_url__isnull=False,
                author=test_user
            ).order_by('-created_at')[:5]
            
            if recent_news.exists():
                self.stdout.write(f"\nПоследние созданные новости:")
                for news in recent_news:
                    self.stdout.write(f"  - {news.title[:60]}...")
                    self.stdout.write(f"    URL: {news.source_url}")
                    self.stdout.write(f"    Статус: {news.status}")
                    self.stdout.write(f"    Создано: {news.created_at.strftime('%d.%m.%Y %H:%M:%S')}")
            
            success = error_count == 0
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nОШИБКА при выполнении поиска:"))
            self.stdout.write(self.style.ERROR(f"  {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
            success = False
        
        # Устанавливаем дату последнего поиска
        if options['set_date']:
            try:
                target_date = date.fromisoformat(options['set_date'])
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Неверный формат даты: {options['set_date']}. Используйте YYYY-MM-DD"))
                return
        else:
            # По умолчанию устанавливаем на 08.12.2025
            target_date = date(2025, 12, 8)
        
        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS("УСТАНОВКА ДАТЫ ПОСЛЕДНЕГО ПОИСКА"))
        self.stdout.write("=" * 60)
        
        NewsDiscoveryRun.update_last_search_date(target_date)
        last_date = NewsDiscoveryRun.get_last_search_date()
        
        self.stdout.write(f"\nДата последнего поиска установлена на: {last_date.strftime('%d.%m.%Y')}")
        
        if success:
            self.stdout.write(f"\n{'=' * 60}")
            self.stdout.write(self.style.SUCCESS("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО"))
            self.stdout.write("=" * 60)
        else:
            self.stdout.write(f"\n{'=' * 60}")
            self.stdout.write(self.style.ERROR("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО С ОШИБКАМИ"))
            self.stdout.write("=" * 60)
