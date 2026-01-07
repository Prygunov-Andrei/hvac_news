"""
Команда для исправления проблемных HTTPS ссылок.
Некоторые сайты не поддерживают HTTPS или имеют проблемы с SSL,
но работают через HTTP. Браузеры автоматически обновляют HTTP на HTTPS,
но при прямом переходе на HTTPS возникает ошибка.
"""
import logging
import requests
import urllib3
from urllib.parse import urlparse, urlunparse
from django.core.management.base import BaseCommand
from references.models import NewsResource

# Отключаем предупреждения о небезопасных SSL соединениях
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix HTTPS URLs that should be HTTP'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually changing',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force change all HTTPS to HTTP (not recommended)',
        )
        parser.add_argument(
            '--test',
            type=int,
            help='Test only first N resources',
        )

    def handle(self, *args, **options):
        resources = NewsResource.objects.all()
        
        if options['test']:
            resources = resources[:options['test']]
        
        total = resources.count()
        self.stdout.write(f'Checking {total} resources...\n')
        
        fixed_count = 0
        tested_count = 0
        error_count = 0
        
        for idx, resource in enumerate(resources, 1):
            if idx % 10 == 0:
                self.stdout.write(f'Processed {idx}/{total}...')
            
            original_url = resource.url
            parsed = urlparse(original_url)
            
            # Пропускаем если уже HTTP
            if parsed.scheme == 'http':
                continue
            
            # Пропускаем если не HTTPS
            if parsed.scheme != 'https':
                continue
            
            tested_count += 1
            
            # Проверяем доступность HTTPS
            https_works = self._test_url(original_url)
            
            if https_works:
                # HTTPS работает, оставляем как есть
                continue
            
            # HTTPS не работает, проверяем HTTP
            http_url = urlunparse(('http', parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
            http_works = self._test_url(http_url)
            
            if http_works:
                self.stdout.write(f'\n[{idx}] {resource.name}')
                self.stdout.write(f'  HTTPS не работает: {original_url}')
                self.stdout.write(f'  HTTP работает: {http_url}')
                
                if not options['dry_run']:
                    resource.url = http_url
                    resource.save()
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Исправлено'))
                    fixed_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f'  [DRY RUN] Будет изменено на HTTP'))
                    fixed_count += 1
            else:
                # Оба не работают - возможно временная проблема
                self.stdout.write(f'\n[{idx}] {resource.name}')
                self.stdout.write(self.style.WARNING(f'  ⚠ HTTPS не работает, но HTTP тоже не отвечает'))
                error_count += 1
        
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS(f'Проверка завершена!'))
        self.stdout.write(f'  Проверено HTTPS ссылок: {tested_count}')
        self.stdout.write(f'  Исправлено: {fixed_count}')
        self.stdout.write(f'  Ошибок: {error_count}')
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('\nЭто был DRY RUN. Для применения изменений запустите без --dry-run'))

    def _test_url(self, url, timeout=5):
        """Проверяет доступность URL"""
        try:
            # Пробуем HEAD запрос
            response = requests.head(
                url, 
                timeout=timeout, 
                allow_redirects=True, 
                verify=False,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            # Проверяем что получили ответ (даже если это редирект или ошибка)
            return response.status_code < 500
        except requests.exceptions.SSLError as e:
            # SSL ошибка - значит HTTPS не поддерживается или есть проблемы с сертификатом
            logger.debug(f"SSL Error for {url}: {str(e)}")
            return False
        except requests.exceptions.ConnectionError as e:
            # Ошибка подключения - возможно порт закрыт или сайт недоступен
            logger.debug(f"Connection Error for {url}: {str(e)}")
            return False
        except requests.exceptions.Timeout:
            # Таймаут
            logger.debug(f"Timeout for {url}")
            return False
        except Exception as e:
            logger.debug(f"Error testing {url}: {str(e)}")
            return False
