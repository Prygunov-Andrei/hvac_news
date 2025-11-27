import zipfile
import os
import re
import shutil
from datetime import datetime
from django.conf import settings
from django.core.files import File
from django.utils import timezone
from .models import NewsPost, NewsMedia

class NewsImportService:
    def __init__(self, zip_path, user=None):
        self.zip_path = zip_path
        self.user = user
        self.temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_import')
        self.lang_map = {
            '[RU]': 'ru',
            '[EN]': 'en',
            '[DE]': 'de',
            '[PT]': 'pt'
        }

    def process(self):
        try:
            self._extract_zip()
            md_content, media_files = self._read_content()
            
            # Split content into multiple news blocks
            news_blocks = self._split_into_news_blocks(md_content)
            
            created_posts = []
            for block_content in news_blocks:
                parsed_data = self._parse_markdown(block_content)
                news_post = self._create_news_post(parsed_data)
                self._process_media(news_post, media_files, parsed_data)
                created_posts.append(news_post)
            
            return created_posts[0] if created_posts else None
        finally:
            self._cleanup()

    def _split_into_news_blocks(self, content):
        """
        Splits the full markdown content into separate news blocks.
        Separator: === NEWS START ===
        """
        separator = "=== NEWS START ==="
        if separator not in content:
            # Fallback for single news file
            return [content]
            
        blocks = []
        parts = content.split(separator)
        for part in parts:
            if part.strip():
                blocks.append(part.strip())
        return blocks

    def _extract_zip(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir)
        
        with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
            zip_ref.extractall(self.temp_dir)

    def _read_content(self):
        md_file = None
        media_files = {} # filename -> full_path
        
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                if file.endswith('.md') and not md_file:
                    md_file = os.path.join(root, file)
                elif not file.startswith('.') and not file.endswith('.DS_Store'): # Skip system files
                    media_files[file] = os.path.join(root, file)
        
        if not md_file:
            raise ValueError("No .md file found in the archive")

        content = None
        encodings_to_try = ['utf-8', 'cp1251', 'latin1']
        
        for encoding in encodings_to_try:
            try:
                with open(md_file, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
                
        if content is None:
            raise ValueError(f"Could not decode .md file. Please save it as UTF-8.")
            
        return content, media_files

    def _parse_markdown(self, content):
        """
        Splits content by language headers # [RU], # [EN], etc.
        Extracts metadata from YAML frontmatter.
        """
        data = {
            'common': {},
            'langs': {}
        }

        # Split lines and remove empty leading lines
        lines = content.split('\n')
        while lines and not lines[0].strip():
            lines.pop(0)
            
        if not lines:
            return data

        current_lang = None
        buffer = []
        
        meta_lines = []
        body_start_index = 0
        
        # Flexible YAML parsing:
        # Case 1: Starts with ---
        if lines[0].strip() == '---':
            for i, line in enumerate(lines[1:]):
                if line.strip() == '---':
                    body_start_index = i + 2
                    break
                meta_lines.append(line)
        # Case 2: Starts immediately with key: value (no --- guard, common user mistake)
        # We treat lines as metadata until we hit an empty line or a # Header
        elif ':' in lines[0] and not lines[0].strip().startswith('#'):
             for i, line in enumerate(lines):
                if not line.strip() or line.strip().startswith('#') or line.strip() == '---':
                    body_start_index = i
                    if line.strip() == '---': body_start_index += 1 # skip separator if found later
                    break
                meta_lines.append(line)
        
        # Parse metadata
        for line in meta_lines:
            if ':' in line:
                key, val = line.split(':', 1)
                data['common'][key.strip()] = val.strip()

        # Parse Body
        for line in lines[body_start_index:]:
            stripped = line.strip()
            
            # Check if line indicates a language section
            # e.g. "# [RU]" or "[RU]"
            found_lang = None
            for lang_tag, lang_code in self.lang_map.items():
                if lang_tag in stripped:
                    found_lang = lang_code
                    break
            
            if found_lang:
                if current_lang:
                    data['langs'][current_lang] = '\n'.join(buffer).strip()
                current_lang = found_lang
                buffer = []
            else:
                buffer.append(line)
        
        # Flush last buffer
        if current_lang:
            data['langs'][current_lang] = '\n'.join(buffer).strip()

        return data

    def _create_news_post(self, data):
        # Extract date
        pub_date = timezone.now()
        if 'date' in data['common']:
            try:
                # Try parsing "YYYY-MM-DD HH:MM"
                parsed = datetime.strptime(data['common']['date'], '%Y-%m-%d %H:%M')
                pub_date = timezone.make_aware(parsed)
            except ValueError:
                pass

        # Prepare creation args
        create_kwargs = {
            'pub_date': pub_date,
            'author': self.user
        }

        # Fill translatable fields
        for lang, content in data['langs'].items():
            # Extract Title (first h1-h6 or first line)
            lines = content.split('\n')
            title = "Untitled"
            body = content
            
            # Try to find a title in the first few lines
            for i, line in enumerate(lines[:5]):
                if line.strip().startswith('#'):
                    title = line.strip().lstrip('#').strip()
                    # Remove title from body to avoid duplication? 
                    # Let's keep it or remove it based on requirement. 
                    # Usually standard MD has title inside. 
                    # Let's keep the body as is for full control.
                    break
            
            create_kwargs[f'title_{lang}'] = title
            create_kwargs[f'body_{lang}'] = body

        # Create instance
        return NewsPost.objects.create(**create_kwargs)

    def _process_media(self, news_post, media_files, parsed_data):
        # 1. Identify which files are actually used in this news post
        used_files = set()
        for lang in self.lang_map.values():
            body = getattr(news_post, f'body_{lang}', '') or ''
            for filename in media_files.keys():
                if filename in body:
                    used_files.add(filename)

        # 2. Upload ONLY used media files to NewsMedia
        file_url_map = {} # original_name -> new_url

        for filename in used_files:
            path = media_files[filename]
            media_type = 'video' if filename.endswith(('.mp4', '.mov', '.avi')) else 'image'
            
            with open(path, 'rb') as f:
                django_file = File(f, name=filename)
                news_media = NewsMedia.objects.create(
                    news_post=news_post,
                    file=django_file,
                    media_type=media_type,
                    original_name=filename
                )
                file_url_map[filename] = news_media.file.url

        # 3. Replace links in Body for all languages
        for lang in self.lang_map.values():
            field_name = f'body_{lang}'
            body = getattr(news_post, field_name, '')
            if not body:
                continue

            # Replace Images: ![Alt](filename.jpg) -> ![Alt](/media/news/...)
            # Replace Videos: [[filename.mp4]] -> <video src="/media/news/..."></video> (or custom tag)
            
            new_body = body
            for original_name, new_url in file_url_map.items():
                # Regex for markdown image: ![...](original_name)
                # We escape original_name because it might contain dots
                escaped_name = re.escape(original_name)
                
                # Replace Images
                new_body = re.sub(
                    fr'!\[(.*?)\]\({escaped_name}\)',
                    fr'![\1]({new_url})',
                    new_body
                )
                
                # Replace Wiki-style Video links or just raw links
                # Pattern: [[original_name]]
                video_tag = f'<video controls src="{new_url}" width="100%"></video>'
                new_body = new_body.replace(f'[[{original_name}]]', video_tag)

            setattr(news_post, field_name, new_body)
        
        news_post.save()

    def _cleanup(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

