from django.contrib import admin
from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'message_preview', 'created_at', 'is_processed')
    list_filter = ('is_processed', 'created_at')
    search_fields = ('email', 'name', 'message')
    readonly_fields = ('created_at',)
    list_editable = ('is_processed',)
    
    def message_preview(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message Preview'
