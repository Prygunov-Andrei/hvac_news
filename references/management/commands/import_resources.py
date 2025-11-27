import re
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from references.models import NewsResource

class Command(BaseCommand):
    help = 'Import news resources from Markdown file'

    def handle(self, *args, **options):
        file_path = os.path.join(settings.BASE_DIR, 'Global HVAC & Refrigeration News Resources.md')
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.readlines()

        count_resources = 0

        for line in content:
            line = line.strip()
            
            # Skip empty lines, headers, separators
            if not line or not line.startswith('|') or line.startswith('| :') or line.startswith('| --') or line.startswith('|--'):
                continue

            # Split by pipe |
            raw_cells = line.split('|')
            
            # Remove first and last elements if they are empty
            if raw_cells and raw_cells[0].strip() == '':
                raw_cells.pop(0)
            if raw_cells and raw_cells[-1].strip() == '':
                raw_cells.pop(-1)
            
            cells = [c.strip() for c in raw_cells]
            
            # Skip header row (contains "Resource Name")
            if not cells or "Resource Name" in cells[0] or "---" in cells[0]:
                continue

            # Expected format: | Resource Name | News / Feed URL | Type | Short Description |
            if len(cells) < 4:
                continue

            raw_name = cells[0].replace('**', '')
            url_str = cells[1].replace('`', '')
            resource_type = cells[2]
            description = cells[3]

            # Clean name (remove brackets if any, though in this file usually simple names or with country code)
            name = raw_name.strip()
            
            # Clean URL (sometimes multiple, take first)
            url = url_str.split(' ')[0] if url_str else ''
            if not url.startswith('http'):
                url = ''

            # Determine language
            is_russian = bool(re.search('[а-яА-Я]', description))

            # Format description to include Type
            full_description = f"[{resource_type}] {description}"

            defaults = {
                'url': url,
            }

            if is_russian:
                defaults['description_ru'] = full_description
                defaults['description'] = full_description
            else:
                defaults['description_en'] = full_description
                defaults['description'] = full_description

            # Create or Update
            resource, created = NewsResource.objects.get_or_create(
                name=name,
                defaults=defaults
            )
            
            if not created:
                for key, value in defaults.items():
                    setattr(resource, key, value)
                resource.save()

            if created:
                count_resources += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count_resources} news resources.'))

