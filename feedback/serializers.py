from rest_framework import serializers
from .models import Feedback


class FeedbackSerializer(serializers.ModelSerializer):
    captcha = serializers.CharField(write_only=True, required=True, help_text="CAPTCHA response token")

    class Meta:
        model = Feedback
        fields = ('id', 'email', 'name', 'message', 'captcha', 'created_at')
        read_only_fields = ('id', 'created_at')

