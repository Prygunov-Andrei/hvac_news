"""
Management команда для удаления всех черновиков новостей.
"""
from django.core.management.base import BaseCommand
from news.models import NewsPost


class Command(BaseCommand):
    help = 'Удаляет все новости со статусом "draft"'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать количество черновиков без удаления',
        )

    def handle(self, *args, **options):
        drafts = NewsPost.objects.filter(status='draft')
        count = drafts.count()
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(f'Найдено черновиков: {count}')
            )
            return
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('Черновиков не найдено')
            )
            return
        
        # Удаляем все черновики
        deleted_count, _ = drafts.delete()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Успешно удалено черновиков: {deleted_count}'
            )
        )
