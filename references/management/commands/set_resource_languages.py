"""
Команда для автоматического заполнения языков источников на основе их секций
"""
from django.core.management.base import BaseCommand
from references.models import NewsResource

# Маппинг секций на языки
SECTION_LANGUAGE_MAP = {
    # Русскоязычные регионы
    'Russian Federation (Ресурсы РФ)': 'ru',
    'CIS (Ресурсы стран СНГ)': 'ru',
    
    # Англоязычные регионы
    'North America and Latin America': 'en',  # Большинство - английский
    'Europe & Global Specialized': 'en',  # Большинство - английский
    'Asia & Pacific': 'en',  # Большинство - английский
    'Global / Multi-Regional (Глобальные/Многорегиональные)': 'en',
    'Specialized Niche Resources (Специализированные Нишевые Ресурсы)': 'en',
    'Blogs & Newsletters (Блоги и рассылки)': 'en',
    'Podcasts (Подкасты)': 'en',
    'Academic Resources (Академические ресурсы)': 'en',
    
    # Испаноязычные регионы
    # (будут обработаны отдельно для Latin America)
    
    # Другие языки
    'Turkey (Турция)': 'tr',
    'Middle East (Ближний Восток)': 'ar',
    'Africa (Африка)': 'en',  # Большинство - английский
}

# Дополнительные правила для определения языка по URL или названию
def detect_language_from_url(url: str, name: str, section: str = None) -> str:
    """Определяет язык по URL или названию источника"""
    url_lower = url.lower()
    name_lower = name.lower()
    
    # Испанский - только явные признаки
    # Домены с высокой вероятностью испанского языка
    spanish_domains_high = ['.es', '.mx']  # Испания и Мексика - точно испанский
    spanish_keywords = ['español', 'espanol', 'revista clima', 'aire acondicionado', 'refrigeración', 'latinoamérica', 'latinoamerica']
    
    # Проверяем домены с высокой вероятностью
    if any(domain in url_lower for domain in spanish_domains_high):
        return 'es'
    
    # Проверяем ключевые слова в названии (более строго)
    if any(keyword in name_lower for keyword in spanish_keywords):
        return 'es'
    
    # Для Latin America - проверяем домены стран
    if section == 'North America and Latin America':
        latin_domains = ['.ar', '.co', '.cl', '.pe', '.ve', '.ec', '.cr', '.uy', '.py']
        if any(domain in url_lower for domain in latin_domains):
            # Но исключаем известные английские сайты
            if not any(exclude in url_lower for exclude in ['achrnews.com', 'hvac.com', 'contractingbusiness.com', 'hvacrnews.com']):
                return 'es'
    
    # Немецкий
    if any(domain in url_lower for domain in ['.de', '.at', '.ch']):
        return 'de'
    if any(word in name_lower for word in ['german', 'deutsch', 'klima']):
        return 'de'
    
    # Португальский
    if any(domain in url_lower for domain in ['.pt', '.br']):
        return 'pt'
    if any(word in name_lower for word in ['português', 'portugues', 'brasil']):
        return 'pt'
    
    # Французский
    if any(domain in url_lower for domain in ['.fr', '.be', '.ch']):
        return 'fr'
    if any(word in name_lower for word in ['french', 'français', 'france']):
        return 'fr'
    
    # Итальянский
    if '.it' in url_lower:
        return 'it'
    if any(word in name_lower for word in ['italiano', 'italia']):
        return 'it'
    
    # Турецкий
    if '.tr' in url_lower:
        return 'tr'
    
    # Арабский
    if any(domain in url_lower for domain in ['.sa', '.ae', '.eg']):
        return 'ar'
    
    # Китайский
    if any(domain in url_lower for domain in ['.cn', '.tw', '.hk']):
        return 'zh'
    
    # Японский
    if '.jp' in url_lower:
        return 'ja'
    
    # Корейский
    if '.kr' in url_lower:
        return 'ko'
    
    # По умолчанию английский
    return 'en'


class Command(BaseCommand):
    help = 'Автоматически заполняет языки источников на основе их секций и URL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет изменено без сохранения',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Перезаписать уже установленные языки',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write("=" * 80)
        self.stdout.write("ЗАПОЛНЕНИЕ ЯЗЫКОВ ИСТОЧНИКОВ")
        self.stdout.write("=" * 80)
        
        resources = NewsResource.objects.all()
        updated_count = 0
        skipped_count = 0
        
        for resource in resources:
            # Если язык уже установлен и не force - пропускаем
            if resource.language and resource.language != 'en' and not force:
                skipped_count += 1
                continue
            
            # Определяем язык
            language = None
            
            # 1. По секции
            if resource.section in SECTION_LANGUAGE_MAP:
                language = SECTION_LANGUAGE_MAP[resource.section]
            
            # 2. По URL и названию (только для определенных секций или если язык не определен)
            # Для Latin America - проверяем испанский
            if resource.section == 'North America and Latin America':
                detected = detect_language_from_url(resource.url, resource.name, resource.section)
                if detected == 'es':
                    language = 'es'
            
            # Для других секций - только если язык не определен
            if not language or language == 'en':
                detected = detect_language_from_url(resource.url, resource.name, resource.section)
                # Используем обнаруженный язык только если он не английский
                if detected != 'en':
                    language = detected
            
            # 3. По умолчанию английский
            if not language:
                language = 'en'
            
            # Обновляем только если изменился
            if resource.language != language:
                if not dry_run:
                    resource.language = language
                    resource.save()
                updated_count += 1
                self.stdout.write(
                    f"{'[DRY RUN] ' if dry_run else ''}"
                    f"✓ {resource.name[:50]:50s} | {resource.section or 'N/A':30s} | {resource.language} → {language}"
                )
        
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"Обработано: {resources.count()}")
        self.stdout.write(f"Обновлено: {updated_count}")
        self.stdout.write(f"Пропущено: {skipped_count}")
        if dry_run:
            self.stdout.write("\n⚠️  DRY RUN - изменения не сохранены!")
            self.stdout.write("Запустите без --dry-run для применения изменений")
        else:
            self.stdout.write("\n✅ Изменения сохранены!")
