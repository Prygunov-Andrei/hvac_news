import re
import os
from urllib.parse import urlparse
from django.core.management.base import BaseCommand
from django.conf import settings
from references.models import Manufacturer, Brand

class Command(BaseCommand):
    help = 'Import manufacturers and brands from Markdown file'

    def handle(self, *args, **options):
        file_path = os.path.join(settings.BASE_DIR, 'Global HVAC Manufacturers Database.md')
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.readlines()

        current_region = "Global"
        
        # Regex patterns
        header_pattern = re.compile(r'^##\s+(.*)') # Matches ## Header
        subheader_pattern = re.compile(r'^###\s+(.*)') # Matches ### Subheader
        table_row_pattern = re.compile(r'^\|') # Matches lines starting with |

        count_manufacturers = 0
        count_brands = 0

        for line in content:
            line = line.strip()
            
            # Skip empty lines and table separators
            if not line or line.startswith('| :') or line.startswith('| --') or line.startswith('|--'):
                continue

            # Detect Region from Headers
            header_match = header_pattern.match(line)
            if header_match:
                current_region = header_match.group(1).strip()
                # Clean up emojis and parentheses if needed
                continue
            
            subheader_match = subheader_pattern.match(line)
            if subheader_match:
                current_region = subheader_match.group(1).strip()
                continue

            # Process Table Row
            if line.startswith('|'):
                # Split by pipe |
                # We need to keep empty strings to preserve column index, but we can strip the result
                raw_cells = line.split('|')
                
                # Remove first and last elements if they are empty (due to leading/trailing pipe)
                if raw_cells and raw_cells[0].strip() == '':
                    raw_cells.pop(0)
                if raw_cells and raw_cells[-1].strip() == '':
                    raw_cells.pop(-1)
                
                cells = [c.strip() for c in raw_cells]
                
                # Skip header row (contains "Company", "Entity")
                if not cells or "Company" in cells[0] or "Entity" in cells[0] or "---" in cells[0]:
                    continue

                # Expected format: | Company | Key Brands | URL | Description |
                # Now cells should have length 4 even if brands are empty
                if len(cells) < 4:
                    # Try to handle inconsistent rows if any
                    continue

                # Extract data
                raw_name = cells[0].replace('**', '') # Remove bold markdown
                brands_str = cells[1]
                url_str = cells[2].replace('`', '') # Remove code blocks
                description = cells[3]

                # Clean name (sometimes it has location in brackets, e.g. "Name (Country)")
                name = raw_name.split('(')[0].strip()
                
                # Clean URL (extract root domain)
                website_url = ''
                if url_str.startswith('http'):
                    try:
                        parsed_url = urlparse(url_str)
                        # Reconstruct basic URL: scheme + netloc (domain)
                        website_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    except Exception:
                        website_url = url_str # Fallback if parsing fails

                # Determine language of description (simple check for Cyrillic)
                is_russian = bool(re.search('[а-яА-Я]', description))
                
                defaults = {
                    'region': current_region,
                    'website_1': website_url,
                }
                
                if is_russian:
                    defaults['description_ru'] = description
                    defaults['description'] = description # Default fallback
                else:
                    defaults['description_en'] = description
                    defaults['description'] = description # Default fallback

                # Create or Update Manufacturer
                manufacturer, created = Manufacturer.objects.get_or_create(
                    name=name,
                    defaults=defaults
                )
                
                if not created:
                    # Update fields if exists
                    for key, value in defaults.items():
                        setattr(manufacturer, key, value)
                    manufacturer.save()

                if created:
                    count_manufacturers += 1

                # Process Brands
                if brands_str:
                    brands_list = [b.strip() for b in brands_str.split(',') if b.strip()]
                    for brand_name in brands_list:
                        # Check if description has brand specific info? No, description is for Manufacturer.
                        # So brands will have empty description initially.
                        brand, b_created = Brand.objects.get_or_create(
                            name=brand_name,
                            manufacturer=manufacturer
                        )
                        if b_created:
                            count_brands += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count_manufacturers} manufacturers and {count_brands} brands.'))
