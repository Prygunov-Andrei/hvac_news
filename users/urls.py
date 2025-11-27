from django.urls import path
from .views import RegistrationView, MeView

urlpatterns = [
    path('', RegistrationView.as_view(), name='register'),
    path('me/', MeView.as_view(), name='me'),
]
