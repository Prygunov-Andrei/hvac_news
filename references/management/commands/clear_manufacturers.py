from django.core.management.base import BaseCommand
from references.models import Manufacturer, Brand

class Command(BaseCommand):
    help = 'Clear all manufacturers and brands from database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            confirm = input('This will delete ALL manufacturers and brands. Are you sure? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                return

        brand_count = Brand.objects.count()
        manufacturer_count = Manufacturer.objects.count()
        
        Brand.objects.all().delete()
        Manufacturer.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS(f'Deleted {manufacturer_count} manufacturers and {brand_count} brands.'))
