from django.test import TestCase
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock
from .models import Feedback


class FeedbackTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('feedback.views.verify_captcha')
    @patch('feedback.views.send_mail')
    def test_create_feedback_success(self, mock_send_mail, mock_verify_captcha):
        """Успешная отправка обратной связи"""
        mock_verify_captcha.return_value = True
        mock_send_mail.return_value = True
        
        response = self.client.post('/api/feedback/', {
            'email': 'test@example.com',
            'name': 'Test User',
            'message': 'Test message',
            'captcha': 'valid_token'
        })
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Feedback.objects.count(), 1)
        feedback = Feedback.objects.first()
        self.assertEqual(feedback.email, 'test@example.com')
        self.assertEqual(feedback.name, 'Test User')
        self.assertEqual(feedback.message, 'Test message')
        
        # Проверяем, что email был отправлен
        mock_send_mail.assert_called_once()

    @patch('feedback.views.verify_captcha')
    def test_create_feedback_requires_captcha(self, mock_verify_captcha):
        """Обратная связь требует валидную CAPTCHA"""
        mock_verify_captcha.return_value = False
        
        response = self.client.post('/api/feedback/', {
            'email': 'test@example.com',
            'message': 'Test message',
            'captcha': 'invalid_token'
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('captcha', response.data)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_create_feedback_missing_captcha(self):
        """Обратная связь требует поле captcha"""
        response = self.client.post('/api/feedback/', {
            'email': 'test@example.com',
            'message': 'Test message'
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('captcha', response.data)

    @patch('feedback.views.verify_captcha')
    @patch('feedback.views.send_mail')
    def test_create_feedback_email_sent(self, mock_send_mail, mock_verify_captcha):
        """Email отправляется администратору"""
        mock_verify_captcha.return_value = True
        mock_send_mail.return_value = True
        
        response = self.client.post('/api/feedback/', {
            'email': 'test@example.com',
            'name': 'Test User',
            'message': 'Test message',
            'captcha': 'valid_token'
        })
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_send_mail.assert_called_once()
        call_args = mock_send_mail.call_args
        # send_mail вызывается как send_mail(subject, message, from_email, recipient_list, ...)
        self.assertIn('New feedback', call_args[0][0])  # subject - первый позиционный аргумент
        self.assertIn('test@example.com', call_args[0][1])  # message - второй позиционный аргумент
