import logging
from django.core.management.base import BaseCommand
from references.models import NewsResource
from news.translation_service import TranslationService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Translate all news resources descriptions to all supported languages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force translation even if translation already exists',
        )
        parser.add_argument(
            '--lang',
            type=str,
            help='Translate only to specific language (en, de, pt)',
        )

    def handle(self, *args, **options):
        translation_service = TranslationService()
        
        if not translation_service.enabled:
            self.stdout.write(self.style.ERROR('Translation is disabled. Set TRANSLATION_ENABLED=True and TRANSLATION_API_KEY in settings.'))
            return
        
        resources = NewsResource.objects.all()
        total = resources.count()
        self.stdout.write(f'Found {total} resources to translate.')
        
        target_languages = ['en', 'de', 'pt']
        if options['lang']:
            if options['lang'] not in target_languages:
                self.stdout.write(self.style.ERROR(f'Invalid language: {options["lang"]}. Use: en, de, pt'))
                return
            target_languages = [options['lang']]
        
        translated_count = 0
        skipped_count = 0
        error_count = 0
        
        for idx, resource in enumerate(resources, 1):
            self.stdout.write(f'\n[{idx}/{total}] Processing: {resource.name}')
            
            # Get source description (Russian)
            source_description = resource.description_ru or resource.description
            
            if not source_description or not source_description.strip():
                self.stdout.write(self.style.WARNING(f'  Skipping: no description found'))
                skipped_count += 1
                continue
            
            # Translate to each target language
            for target_lang in target_languages:
                field_name = f'description_{target_lang}'
                current_translation = getattr(resource, field_name, None)
                
                # Skip if translation exists and --force is not set
                if current_translation and current_translation.strip() and not options['force']:
                    self.stdout.write(f'  {target_lang}: already translated, skipping')
                    continue
                
                self.stdout.write(f'  Translating to {target_lang}...', ending='')
                
                try:
                    translated = translation_service.translate(
                        source_description,
                        source_lang='ru',
                        target_lang=target_lang
                    )
                    
                    if translated:
                        setattr(resource, field_name, translated)
                        self.stdout.write(self.style.SUCCESS(f' ✓'))
                    else:
                        self.stdout.write(self.style.WARNING(f' ✗ (empty result)'))
                        error_count += 1
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f' ✗ Error: {str(e)}'))
                    logger.error(f'Translation error for resource {resource.id} to {target_lang}: {str(e)}')
                    error_count += 1
            
            # Save resource after all translations
            try:
                resource.save()
                translated_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error saving resource: {str(e)}'))
                error_count += 1
        
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'Translation completed!'))
        self.stdout.write(f'  Translated: {translated_count}')
        self.stdout.write(f'  Skipped: {skipped_count}')
        self.stdout.write(f'  Errors: {error_count}')
