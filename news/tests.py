import os
import shutil
import tempfile
import zipfile
from django.test import TestCase
from django.core.files import File
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from .models import NewsPost, NewsMedia, Comment
from .services import NewsImportService

User = get_user_model()

class NewsImportTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@news.com', password='password')
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_import_service(self):
        # Create a dummy zip file content
        md_content = """---
date: 2023-12-25 12:00
---

# [RU]
# Заголовок
Текст новости с картинкой ![Img](test.jpg)

# [EN]
# Title
News body with video [[video.mp4]]
"""
        # Create files
        md_path = os.path.join(self.temp_dir, 'post.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        img_path = os.path.join(self.temp_dir, 'test.jpg')
        with open(img_path, 'wb') as f:
            f.write(b'fakeimage')
            
        vid_path = os.path.join(self.temp_dir, 'video.mp4')
        with open(vid_path, 'wb') as f:
            f.write(b'fakevideo')

        # Zip them
        zip_path = os.path.join(self.temp_dir, 'test.zip')
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.write(md_path, 'post.md')
            z.write(img_path, 'test.jpg')
            z.write(vid_path, 'video.mp4')

        # Run Service
        service = NewsImportService(zip_path, user=self.user)
        news_post = service.process()

        # Assertions
        self.assertEqual(NewsPost.objects.count(), 1)
        self.assertEqual(news_post.title_ru, 'Заголовок')
        self.assertEqual(news_post.title_en, 'Title')
        
        # Check Media
        self.assertEqual(news_post.media.count(), 2)
        
        # Check link replacement
        self.assertIn('/media/news/', news_post.body_ru)
        self.assertIn('video', news_post.body_en)
        self.assertIn('src="/media/news/', news_post.body_en)

    def test_future_post_visibility(self):
        # Past post
        NewsPost.objects.create(
            title="Past", 
            body="Body", 
            pub_date=timezone.now() - timezone.timedelta(days=1)
        )
        # Future post
        NewsPost.objects.create(
            title="Future", 
            body="Body", 
            pub_date=timezone.now() + timezone.timedelta(days=1)
        )
        
        response = self.client.get('/api/news/')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], "Past")


class CommentTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email='user1@test.com', password='password')
        self.user2 = User.objects.create_user(email='user2@test.com', password='password')
        self.news_post = NewsPost.objects.create(
            title="Test News",
            body="Test Body",
            pub_date=timezone.now() - timezone.timedelta(days=1)
        )
        self.client = APIClient()

    def test_create_comment_requires_auth(self):
        """Незарегистрированный пользователь не может создать комментарий"""
        response = self.client.post('/api/comments/', {
            'news_post': self.news_post.id,
            'text': 'Test comment'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_comment_authenticated(self):
        """Авторизованный пользователь может создать комментарий"""
        self.client.force_authenticate(user=self.user1)
        response = self.client.post('/api/comments/', {
            'news_post': self.news_post.id,
            'text': 'Test comment'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertEqual(Comment.objects.first().author, self.user1)

    def test_read_comments_public(self):
        """Все пользователи могут читать комментарии"""
        comment = Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='Public comment'
        )
        response = self.client.get('/api/comments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, есть ли пагинация или это просто список
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            self.assertEqual(len(data['results']), 1)
        else:
            self.assertEqual(len(data), 1)

    def test_update_own_comment(self):
        """Пользователь может редактировать только свои комментарии"""
        comment = Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='Original text'
        )
        self.client.force_authenticate(user=self.user1)
        response = self.client.patch(f'/api/comments/{comment.id}/', {
            'text': 'Updated text'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.text, 'Updated text')

    def test_cannot_update_other_comment(self):
        """Пользователь не может редактировать чужие комментарии"""
        comment = Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='Original text'
        )
        self.client.force_authenticate(user=self.user2)
        response = self.client.patch(f'/api/comments/{comment.id}/', {
            'text': 'Hacked text'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_own_comment(self):
        """Пользователь может удалять только свои комментарии"""
        comment = Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='To be deleted'
        )
        self.client.force_authenticate(user=self.user1)
        response = self.client.delete(f'/api/comments/{comment.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Comment.objects.count(), 0)

    def test_filter_comments_by_news(self):
        """Фильтрация комментариев по новости"""
        news_post2 = NewsPost.objects.create(
            title="News 2",
            body="Body 2",
            pub_date=timezone.now()
        )
        Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='Comment 1'
        )
        Comment.objects.create(
            news_post=news_post2,
            author=self.user1,
            text='Comment 2'
        )
        response = self.client.get(f'/api/comments/?news_post={self.news_post.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, есть ли пагинация или это просто список
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            self.assertEqual(len(data['results']), 1)
        else:
            self.assertEqual(len(data), 1)
