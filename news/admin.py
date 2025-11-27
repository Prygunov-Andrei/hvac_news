from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.utils.html import format_html
from django import forms
from modeltranslation.admin import TranslationAdmin
from .models import NewsPost, NewsMedia
from .services import NewsImportService

class ImportNewsForm(forms.Form):
    zip_file = forms.FileField()

@admin.register(NewsPost)
class NewsPostAdmin(TranslationAdmin):
    list_display = ('title', 'pub_date', 'author', 'created_at')
    search_fields = ('title',)
    change_list_template = "admin/news_changelist.html"

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
