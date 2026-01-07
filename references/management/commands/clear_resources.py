from django.core.management.base import BaseCommand
from references.models import NewsResource

class Command(BaseCommand):
    help = 'Clear all news resources from database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        count = NewsResource.objects.count()
        
        if count == 0:
            self.stdout.write(self.style.WARNING('No resources found in database.'))
            return
        
        if not options['yes']:
            confirm = input(f'Are you sure you want to delete {count} resources? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                return
        
        NewsResource.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} resources.'))
