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

        count_created = 0
        count_updated = 0
        current_region = ''

        for line in content:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Track region headers (starting with ###)
            if line.startswith('###'):
                # Extract region name (remove ### and emoji if present)
                current_region = re.sub(r'^###\s*[^\s]+\s*', '', line).strip()
                continue
            
            # Skip other markdown headers
            if line.startswith('#'):
                continue
            
            # Expected format: "Название" // "ссылка" // "Описание"
            if ' // ' not in line:
                continue
            
            # Split by " // "
            parts = [part.strip() for part in line.split(' // ')]
            
            # Need at least name and URL
            if len(parts) < 2:
                continue
            
            name = parts[0].strip()
            url = parts[1].strip() if len(parts) > 1 else ''
            description = parts[2].strip() if len(parts) > 2 else ''
            
            # Clean name (remove quotes if present)
            name = name.strip('"\'')
            
            # Clean URL (remove quotes if present, validate)
            url = url.strip('"\'')
            if not url.startswith('http://') and not url.startswith('https://'):
                # Skip invalid URLs
                continue
            
            # Clean description - remove section info if it was added previously
            description = description.strip()
            if description.startswith('[') and ']' in description:
                # Remove section prefix if present
                description = re.sub(r'^\[.*?\]\s*', '', description)
            
            # Create or Update
            resource, created = NewsResource.objects.get_or_create(
                name=name,
                defaults={
                    'url': url,
                    'description': description,
                    'section': current_region,
                }
            )
            
            if not created:
                # Update existing resource
                resource.url = url
                resource.description = description
                resource.section = current_region
                resource.save()
                count_updated += 1
            else:
                count_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully imported {count_created} new resources and updated {count_updated} existing resources.'
            )
        )

