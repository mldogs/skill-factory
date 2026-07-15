# Skill Factory

Коллекция скиллов для [Claude Code](https://claude.com/claude-code). Каждый скилл — самостоятельная папка (`SKILL.md` + скрипты), которая ставится копированием в `.claude/skills/` и вызывается командой `/<имя-скилла>` или естественной фразой.

Репозиторий устроен как каталог по рубрикам; рубрики пополняются.

## Каталог

### 📚 learning — из контента в учебные материалы

Скиллы, которые берут книгу или видео и делают из них интерактивную HTML-страницу для изучения: концепты с диаграммами и иллюстрациями, глоссарий с поиском, вопросы для самопроверки. Страницы двуязычные (русский текст, английская терминология, переключатель RU/EN) и работают локально без сервера — это один HTML-файл с относительными путями к картинкам.

| Скилл | Вход | Выход |
|---|---|---|
| [book-deepdive](learning/book-deepdive/) | Книга (название, автор) | `books/<slug>/` — разбор по частям и темам: концепты с inline-SVG-диаграммами, несколько сгенерированных иллюстраций, глоссарий, Q&A |
| [podcast-deepdive](learning/podcast-deepdive/) | YouTube-эпизод (URL) | `podcasts/<slug>/` — разбор беседы: спикеры, главы со ссылками на нужную секунду видео, цитаты, сверенные с транскриптом, карточки разногласий, глоссарий, Q&A |

Оба скилла работают одинаково: несколько параллельных агентов анализируют источник и проверяют факты друг за другом, результат складывается в один JSON-файл (`book.json` / `podcast.json`, контракт проверяется валидатором по JSON Schema), из которого детерминированный Python-скрипт собирает страницу. Текст и данные живут в JSON, поэтому страницу можно пересобирать сколько угодно раз.

**Пример результата:** [живая страница](https://mldogs.github.io/skill-factory/examples/podcast-deepdive/ai-first-company/ai-first-company.html) — разбор доклада «Как построить AI-First компанию» (Алексей Остриков, 48 мин), собранный скиллом `podcast-deepdive` из YouTube-ссылки. Исходные файлы примера (страница + `podcast.json` + иллюстрации) — в [`examples/podcast-deepdive/ai-first-company/`](examples/podcast-deepdive/ai-first-company/).

## Установка

```bash
git clone https://github.com/mldogs/skill-factory
mkdir -p your-project/.claude/skills
cp -R skill-factory/learning/book-deepdive your-project/.claude/skills/
cp -R skill-factory/learning/podcast-deepdive your-project/.claude/skills/
```

Для установки во все проекты сразу — копируйте в `~/.claude/skills/`. После перезапуска Claude Code скиллы доступны как `/book-deepdive` и `/podcast-deepdive`.

## Зависимости

- **Claude Code** с инструментом Workflow — анализ построен на multi-agent workflow-скриптах.
- **`uv`** — валидаторы схем (`validate_book.py`, `validate_podcast.py`) объявляют зависимость `jsonschema` через PEP 723 и запускаются `uv run`.
- **`yt-dlp`** — только для podcast-deepdive, выкачивает субтитры YouTube.
- **`.env` в корне проекта** — только для генерации иллюстраций:
  ```
  OPEN_ROUTER_API_KEY=sk-or-...
  IMG_MODEL=google/gemini-3.1-flash-image-preview   # опционально
  IMG_STYLE=...                                     # опционально, свой стиль иллюстраций
  ```
  Сгенерированные картинки кешируются на диске и при повторной сборке не запрашиваются заново. Без ключа скиллы работают, страница собирается без иллюстраций (SVG-диаграммы рисуются локально).

## Лицензия

MIT
