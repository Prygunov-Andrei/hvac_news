from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.utils.html import format_html
from django import forms
from modeltranslation.admin import TranslationAdmin
from .models import NewsPost, NewsMedia, Comment, NewsDiscoveryRun, NewsDiscoveryStatus
from .services import NewsImportService

class ImportNewsForm(forms.Form):
    zip_file = forms.FileField()

@admin.register(NewsPost)
class NewsPostAdmin(TranslationAdmin):
    list_display = ('title', 'source_url_link', 'pub_date', 'author', 'status', 'is_no_news_found', 'created_at')
    search_fields = ('title',)
    list_filter = ('status', 'source_language', 'is_no_news_found', 'created_at')
    readonly_fields = ('source_url_link', 'created_at', 'updated_at', 'is_no_news_found')
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'body', 'source_url', 'source_url_link', 'status', 'source_language', 'author', 'pub_date')
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at', 'is_no_news_found'),
            'classes': ('collapse',)
        }),
    )
    change_list_template = "admin/news_changelist.html"
    
    def source_url_link(self, obj):
        """Отображает source_url как кликабельную ссылку"""
        if obj.source_url:
            return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', 
                             obj.source_url, obj.source_url[:60] + '...' if len(obj.source_url) > 60 else obj.source_url)
        return '-'
    source_url_link.short_description = 'Источник'
    source_url_link.admin_order_field = 'source_url'

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('import-zip/', self.import_zip, name='news_import_zip'),
        ]
        return my_urls + urls

    def import_zip(self, request):
        if request.method == "POST":
            form = ImportNewsForm(request.POST, request.FILES)
            if form.is_valid():
                zip_file = request.FILES['zip_file']
                
                # Save zip temporarily
                # Or pass the file object directly if service supports it (service currently expects path)
                # Let's save it to a temporary location
                import tempfile
                import os
                
                # Create a named temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
                    for chunk in zip_file.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name
                
                try:
                    service = NewsImportService(tmp_path, user=request.user)
                    service.process()
                    self.message_user(request, "News imported successfully")
                except Exception as e:
                    self.message_user(request, f"Error: {str(e)}", level="error")
                finally:
                    os.unlink(tmp_path)
                
                return redirect("..")
        else:
            form = ImportNewsForm()
            
        context = {
            'form': form,
            'title': 'Import News from ZIP',
            'opts': self.model._meta,
        }
        return render(request, "admin/import_news.html", context)

@admin.register(NewsMedia)
class NewsMediaAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'media_type', 'news_post')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'news_post', 'text_preview', 'created_at')
    list_filter = ('created_at', 'news_post')
    search_fields = ('text', 'author__email', 'news_post__title')
    readonly_fields = ('created_at', 'updated_at')
    
    def text_preview(self, obj):
        return obj.text[:100] + '...' if len(obj.text) > 100 else obj.text
    text_preview.short_description = 'Text Preview'


@admin.register(NewsDiscoveryRun)
class NewsDiscoveryRunAdmin(admin.ModelAdmin):
    list_display = ('last_search_date', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    list_filter = ('last_search_date',)


@admin.register(NewsDiscoveryStatus)
class NewsDiscoveryStatusAdmin(admin.ModelAdmin):
    list_display = ('status', 'processed_count', 'total_count', 'get_progress_percent_display', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at', 'get_progress_percent_display')
    list_filter = ('status', 'created_at')
    
    def get_progress_percent_display(self, obj):
        return f"{obj.get_progress_percent()}%"
    get_progress_percent_display.short_description = 'Progress'
