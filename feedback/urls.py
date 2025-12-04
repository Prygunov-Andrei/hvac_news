from django.urls import path
from .views import create_feedback

urlpatterns = [
    path('feedback/', create_feedback, name='feedback-create'),
]

