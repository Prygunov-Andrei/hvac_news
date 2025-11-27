# Инструкция по подготовке новостей (Mass Import)

Вы можете загружать одну или несколько новостей в одном `.md` файле.
Все картинки и видео должны лежать в корне архива (рядом с этим файлом).
Скрипт сам найдет нужные файлы для каждой новости.

Разделитель между новостями: `=== NEWS START ===`

---

=== NEWS START ===
date: 2024-01-20 10:00
author: Admin
---

# [RU]
# Заголовок первой новости
Текст первой новости на русском языке.
Можно вставлять картинки: ![Схема](schema_v1.jpg)

# [EN]
# First News Title
Text of the first news in English.
Images work here too: ![Schema](schema_v1.jpg)

=== NEWS START ===
date: 2024-02-15 14:30
---

# [RU]
# Вторая новость: Видеообзор
Здесь мы показываем видео.
[[review.mp4]]

# [EN]
# Second News: Video Review
Here is the video.
[[review.mp4]]

# [DE]
# Zweite Nachricht
Hier ist das Video.
[[review.mp4]]

=== NEWS START ===
date: 2024-03-01 09:00
---

# [RU]
# Третья новость без даты (опубликуется сейчас)
Просто текст.

# [EN]
# Third News
Just text.
