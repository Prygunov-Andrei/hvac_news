from rest_framework import viewsets, permissions
from django.utils import timezone
from .models import NewsPost
from .serializers import NewsPostSerializer

class NewsPostViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NewsPostSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        return NewsPost.objects.filter(pub_date__lte=timezone.now()).order_by('-pub_date')
