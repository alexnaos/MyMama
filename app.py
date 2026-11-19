"""
Литературный сборник — онлайн-архив поэзии и прозы Эллы Гогелиани.

Flask-приложение загружает markdown-файлы из каталогов
md_output/поэзия и md_output/проза (включая вложенные папки),
читает YAML-front matter (title, author, created, description, tags)
и отображает произведения: списки, детальные страницы и поиск.

Весь контент хранится в кодировке UTF-8 — кириллица поддерживается полностью.
"""

import configparser
import io
import os
import re
import time
import urllib.parse
import uuid
import zipfile
from xml.sax.saxutils import escape as xml_escape

import markdown as mdlib
import yaml
from flask import Flask, abort, render_template, request, send_file, send_from_directory
from markupsafe import Markup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MD_OUTPUT_DIR = os.path.join(BASE_DIR, 'md_output')
POETRY_DIR = os.path.join(MD_OUTPUT_DIR, 'поэзия')
PROSE_DIR = os.path.join(MD_OUTPUT_DIR, 'проза')
ARTICLES_DIR = os.path.join(MD_OUTPUT_DIR, 'статьи')

MARKDOWN_EXTENSIONS = ['extra', 'sane_lists', 'nl2br', 'tables', 'fenced_code']

SECTION_NAMES = {'poetry': 'Поэзия', 'prose': 'Проза', 'articles': 'Статьи'}
ROOT_GROUP_LABELS = {
    'poetry': 'Основные стихотворения',
    'prose': 'Основные произведения',
    'articles': 'Статьи',
}

app = Flask(__name__)
app.config.update(
    SECRET_KEY='mama-literary-collection-secret-key',
    TEMPLATES_AUTO_RELOAD=True,
)


# --------------------------------------------------------------------------
# Вспомогательные функции
# --------------------------------------------------------------------------

def _cased(value):
    """Ключ для сортировки строк без учёта регистра (в т.ч. кириллицы)."""
    return str(value or '').casefold()


def ru_plural(number, one, few, many):
    """Русские формы множественного числа: 1 -> one, 2-4 -> few, 5+ -> many."""
    n = abs(int(number))
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not (12 <= n100 <= 14):
        return few
    return many


def _strip_html(html):
    """Убирает HTML-теги и схлопывает подряд идущие пробелы."""
    text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()


# Obsidian/Markdown-ссылки, которые нужно вырезать из «плоского» текста.
# Порядок обработки важен: сначала картинки, потом вики-ссылки.
_MD_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\n]+)\)')       # ![альт](путь)
_OBSIDIAN_IMAGE_RE = re.compile(r'!\[\[([^\]]+)\]\]')          # ![[путь к картинке]]
_OBSIDIAN_WIKILINK_RE = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')  # [[Название|подпись]]


def _wikilink_repl(match):
    """Из [[Название]] или [[Название|подпись]] оставляет читаемый текст."""
    return (match.group(2) or match.group(1)).strip()


def _clean_plain_text(text):
    """Плоский текст без HTML-тегов и без Markdown/Obsidian-ссылок.

    Перед выжимкой удаляются ссылки на картинки (![[…]] и ![…](…)) и
    внутренние вики-ссылки [[…]], иначе в карточке остаётся сырой текст
    вида «static/images/content/Pasted image …».
    """
    text = _OBSIDIAN_IMAGE_RE.sub('', text)
    text = _MD_IMAGE_RE.sub('', text)
    text = _OBSIDIAN_WIKILINK_RE.sub(_wikilink_repl, text)
    return _strip_html(text)


def _excerpt_source(text, limit=480):
    """Краткая выжимка чистого текста (ссылки на картинки вычищены)."""
    clean = _clean_plain_text(text)
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rfind(' ')
    if cut < 120:
        cut = limit
    return clean[:cut].rstrip() + '…'


def _as_text(value, default=''):
    """Значение front matter как строка; списки склеиваются запятыми."""
    if isinstance(value, (list, tuple)):
        value = ', '.join(str(item).strip() for item in value if str(item).strip())
    value = str(value or '').strip()
    return value or default


def _as_list(value):
    """Значение front matter как список строк."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]

SOCIAL_ORDER = ['telegram', 'vkontakte', 'youtube', 'instagram', 'odnoklassniki']
SOCIAL_LABELS = {
    'telegram': 'Telegram',
    'vkontakte': 'ВКонтакте',
    'youtube': 'YouTube',
    'instagram': 'Instagram',
    'odnoklassniki': 'Одноклассники',
}


def load_social_links():
    """Список ссылок на соцсети из config.ini (секция [social]).

    Возвращает только те пункты, у которых указан непустой URL.
    """
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(os.path.join(BASE_DIR, 'config.ini'), encoding='utf-8')
    except (OSError, configparser.Error):
        parser = configparser.ConfigParser(interpolation=None)
    links = []
    if parser.has_section('social'):
        for key in SOCIAL_ORDER:
            value = (parser.get('social', key, fallback='') or '').strip()
            if value:
                links.append({'key': key,
                              'label': SOCIAL_LABELS.get(key, key),
                              'url': value})
    return links


def _get_cover_url(cover_val):
    """Превращает цифру или имя файла из поля cover в правильный URL."""
    cover_val = str(cover_val or '').strip().strip("'\"")
    if not cover_val:
        return ''
    
    # Если написана просто цифра (например, '3')
    if cover_val.isdigit():
        return f"/static/images/covers/Image{cover_val}.jpg"
    
    # Если написано имя файла (например, 'Image3.jpg')
    elif not cover_val.startswith('/') and not cover_val.startswith('http'):
        return f"/static/images/covers/{cover_val}"
        
    return cover_val


FRONTMATTER_RE = re.compile(
    r'\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)\Z',
    re.DOTALL,
)


def _split_frontmatter(body):
    """Разделяет YAML-front matter и тело markdown-файла."""
    match = FRONTMATTER_RE.match(body)
    if not match:
        return {}, body
    meta_text, content = match.group(1), match.group(2)
    try:
        parsed = yaml.safe_load(meta_text)
        meta = parsed if isinstance(parsed, dict) else {}
    except yaml.YAMLError:
        meta = {}
    return meta, content


# --------------------------------------------------------------------------
# Загрузка произведений из markdown-файлов
# --------------------------------------------------------------------------

def _build_work(path, section, folder, folder_label, raw_body, meta):
    """Собирает словарь-карточку произведения из метаданных и тела файла."""
    fallback_title = os.path.splitext(os.path.basename(path))[0]
    return {
        'id': 0,
        'section': section,
        'section_name': SECTION_NAMES[section],
        'title': re.sub(r'\s+', ' ', _as_text(meta.get('title'), fallback_title)),
        'author': _as_text(meta.get('author'), 'Элла Гогелиани'),
        'date': str(meta.get('created') or '')[:10],
        'created': _as_text(meta.get('created')),
        'description': _as_text(meta.get('description')),
        'tags': _as_list(meta.get('tags')),
        'cover': _get_cover_url(meta.get('cover')), # НОВОЕ
        'publish': str(meta.get('publish', 'true')).lower() != 'false', # НОВОЕ
        'folder': folder,
        'folder_label': folder_label,
        'path': path,
        'raw_body': raw_body,
        '_html_cache': None,
        '_excerpt_cache': {},
        '_plain_cache': None,
        '_search_cache': None,
    }


_OBSIDIAN_WIKI_RE = re.compile(r'!\[\[(.*?)\]\]')
_OBSIDIAN_MD_RE = re.compile(r'!\[([^\]]*)\]\(([^)\n]+)\)')


def _obsidian_img_html(alt, raw_path):
    """Из пути в Obsidian-ссылке собирает готовый HTML-тег <img>.

    Возвращает None, если путь не относится к static/ (например, https://…,
    images/…, /static/ уже абсолютный) — в этом случае ссылку не трогаем.
    """
    path = (raw_path or '').strip(" \t\"'")
    if not path.startswith('static/') and not path.startswith('/static/'):
        return None
    # Относительный путь static/... -> абсолютный /static/...
    if path.startswith('static/') and not path.startswith('/'):
        path = '/' + path
    # Пробелы и спецсимволы в URL: 'Pasted image.png' -> 'Pasted%20image.png'
    quoted = urllib.parse.quote(path, safe='/%:')
    # Альт-текст: берём переданный, иначе имя файла без расширения
    alt = (alt or '').strip()
    if not alt:
        alt = os.path.basename(path)
    alt = xml_escape(alt)
    return ('<img class="w-full h-auto rounded-lg my-4" '
            'src="%s" alt="%s">') % (quoted, alt)


def _process_obsidian_images(text):
    """Определяет и превращает Obsidian-ссылки на картинки в теги <img>.

    Исторически в контенте два формата:
      1. Вики-ссылки            ![[static/images/content/Pasted image 2026..png]]
      2. Стандартный Markdown   ![Pasted image](static/images/content/Pasted image 2026..png)

    Для каждой ссылки:
      - извлекаем путь к картинке;
      - если путь начинается с "static/" (без слэша) — делаем "/static/...";
      - кодируем URL через urllib.parse.quote (пробелы -> %20);
      - заменяем ссылку на <img class="w-full h-auto rounded-lg my-4" ...>.

    Прочие пути (http(s)://…, /static/…, images/…) не затрагиваем.
    """
    def _proc_wiki(match):
        content = match.group(1).strip()
        alt, path = None, content
        if '|' in content:  # формат ![[path|альтернативный текст]]
            path, _, alias = content.partition('|')
            alt = alias.strip() or alt
        img = _obsidian_img_html(alt, path)
        return img if img is not None else match.group(0)

    def _proc_md(match):
        img = _obsidian_img_html(match.group(1), match.group(2))
        return img if img is not None else match.group(0)

    text = _OBSIDIAN_WIKI_RE.sub(_proc_wiki, text)
    text = _OBSIDIAN_MD_RE.sub(_proc_md, text)
    return text


def render_markdown(text):
    """Рендерит markdown в HTML."""
    text = _process_obsidian_images(text)  # Obsidian: ![[...]] и ![...](...) -> <img>
    return mdlib.markdown(text, extensions=MARKDOWN_EXTENSIONS)


def work_body_html(work):
    """HTML-версия тела произведения (рендерится один раз и кэшируется)."""
    if work['_html_cache'] is None:
        html = render_markdown(work['raw_body']).strip()
        work['_html_cache'] = html or work['raw_body']
    return work['_html_cache']


def work_plain_text(work):
    """Полный «плоский» текст произведения (из описания или тела файла).

    Разметка и ссылки на картинки удалены, поэтому len(work_plain_text(work))
    — это реальная длина текста, который читает пользователь.
    """
    if work['_plain_cache'] is None:
        source = work['description'] or work['raw_body']
        work['_plain_cache'] = _clean_plain_text(source)
    return work['_plain_cache']

def work_excerpt(work, limit=480):
    """Краткая выжимка текста для карточки произведения.

    Короткий текст возвращается целиком, длинный — срезом по слову
    с многоточием. Кэш разбит по limit, чтобы разные шаблоны (240 и 180)
    не перезаписывали друг друга.
    """
    cache = work['_excerpt_cache']
    if cache.get(limit) is None:
        cache[limit] = _excerpt_source(work_plain_text(work), limit)
    return cache[limit]


def work_is_short(work, threshold=200):
    """True, если текст произведения короткий (не больше threshold символов).

    Используется в шаблонах карточек: короткий текст показываем целиком,
    а кнопку «Читать» — только для длинных произведений.
    """
    return len(work_plain_text(work)) <= threshold


def work_search_text(work):
    """Нормализованный текст для поиска по сборнику."""
    if work['_search_cache'] is None:
        parts = [work['title'], work['author'], work['description'],
                 _clean_plain_text(work['raw_body'])]
        work['_search_cache'] = ' '.join(parts).casefold()
    return work['_search_cache']


def _load_collection(section_dir, section):
    """Рекурсивно загружает все .md файлы из папки раздела."""
    items = []
    for dirpath, dirnames, filenames in os.walk(section_dir):
        dirnames.sort(key=_cased)
        for filename in sorted(filenames, key=_cased):
            if not filename.lower().endswith('.md'):
                continue
            path = os.path.join(dirpath, filename)
            try:
                with open(path, 'r', encoding='utf-8') as handle:
                    raw = handle.read()
            except (OSError, UnicodeDecodeError):
                continue
            meta, body = _split_frontmatter(raw)
            
            # НОВОЕ: Проверяем поле publish. Если false - пропускаем файл.
            if str(meta.get('publish', 'true')).lower() in ('false', '0', 'no'):
                continue
                
            relative_dir = os.path.relpath(dirpath, section_dir)
            if relative_dir == '.':
                folder, folder_label = '', ROOT_GROUP_LABELS[section]
            else:
                folder = relative_dir
                folder_label = relative_dir.replace(os.sep, ' → ')
            items.append(_build_work(path, section, folder, folder_label, body, meta))
    items.sort(key=lambda work: _cased(work['title']))
    for index, work in enumerate(items, start=1):
        work['id'] = index
    return items


POEMS = _load_collection(POETRY_DIR, 'poetry')
PIECES = _load_collection(PROSE_DIR, 'prose')
ARTICLES = _load_collection(ARTICLES_DIR, 'articles')
ALL_WORKS = POEMS + PIECES + ARTICLES


# --------------------------------------------------------------------------
# Автообновление контента: новые/изменённые md-файлы подхватываются
# при следующем запросе без перезапуска сервера.
# --------------------------------------------------------------------------

def _content_signature():
    """Метка текущего состояния markdown-файлов (пути + время + размер)."""
    parts = []
    for base in (POETRY_DIR, PROSE_DIR, ARTICLES_DIR):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort(key=_cased)
            for filename in sorted(filenames, key=_cased):
                if not filename.lower().endswith('.md'):
                    continue
                path = os.path.join(dirpath, filename)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                parts.append((path, stat.st_mtime_ns, stat.st_size))
    return parts


_RELOAD_STATE = {'parts': _content_signature(), 'checked_at': 0.0}


def _reload_if_changed():
    """Перезагружает коллекции, если markdown-файлы изменились."""
    global POEMS, PIECES, ARTICLES, ALL_WORKS
    now = time.time()
    if now - _RELOAD_STATE['checked_at'] < 1.0:
        return
    _RELOAD_STATE['checked_at'] = now
    current = _content_signature()
    if _RELOAD_STATE['parts'] == current:
        return
    POEMS = _load_collection(POETRY_DIR, 'poetry')
    PIECES = _load_collection(PROSE_DIR, 'prose')
    ARTICLES = _load_collection(ARTICLES_DIR, 'articles')
    ALL_WORKS = POEMS + PIECES + ARTICLES
    _RELOAD_STATE['parts'] = current


@app.before_request
def _refresh_content():
    _reload_if_changed()


def _group_by_folder(items):
    """Группирует произведения по вложенным папкам раздела."""
    groups, mapping = [], {}
    for work in items:
        key = work['folder'] or '\0root'
        if key not in mapping:
            entry = (work['folder_label'], [])
            mapping[key] = entry
            groups.append(entry)
        mapping[key][1].append(work)
    return groups


# --------------------------------------------------------------------------
# Помощники для представлений
# --------------------------------------------------------------------------

def _find_item(collection, work_id):
    return next((work for work in collection if work['id'] == work_id), None)


def _neighbors(collection, work):
    position = collection.index(work) if work in collection else 0
    previous = collection[position - 1] if position > 0 else None
    following = collection[position + 1] if position < len(collection) - 1 else None
    return previous, following


@app.context_processor
def _template_helpers():
    """Функции и данные, доступные во всех шаблонах."""
    return {'work_excerpt': work_excerpt,
            'work_body_html': work_body_html,
            'work_plain_text': work_plain_text,
            'work_is_short': work_is_short,
            'ru_plural': ru_plural,
            'social_links': load_social_links()}
# --------------------------------------------------------------------------
# Маршруты сайта
# --------------------------------------------------------------------------

@app.route('/')
def index():
    """Главная страница."""
    return render_template('index.html', active='', title='Элла',
                           description='Осколки чьей-то жизни',
                           poems_count=len(POEMS), pieces_count=len(PIECES))


@app.route('/poetry/')
def poetry():
    """Страница с поэзией."""
    return render_template('poetry.html', active='poetry', title='Поэзия',
                           description='Стихотворения Эллы Гогелиани',
                           groups=_group_by_folder(POEMS), total=len(POEMS))


@app.route('/prose/')
def prose():
    """Страница с прозой."""
    return render_template('prose.html', active='prose', title='Проза',
                           description='Прозаические произведения Эллы Гогелиани',
                           groups=_group_by_folder(PIECES), total=len(PIECES))


@app.route('/pieces/')
def articles():
    """Страница со статьями."""
    return render_template('articles.html', active='articles', title='Статьи',
                           description='Статьи и публицистические заметки',
                           groups=_group_by_folder(ARTICLES), total=len(ARTICLES))


@app.route('/poem/<int:work_id>/')
def poem_detail(work_id):
    """Детальная страница стихотворения."""
    work = _find_item(POEMS, work_id)
    if work is None:
        abort(404)
    previous, following = _neighbors(POEMS, work)
    return render_template('work_detail.html', active='poetry', title=work['title'],
                           work=work, body_html=Markup(work_body_html(work)),
                           section_name='Поэзия', list_url='/poetry/', back_text='Ко всем стихам',
                           detail_prefix='/poem/', previous=previous, following=following,
                           total=len(POEMS))


@app.route('/piece/<int:work_id>/')
def piece_detail(work_id):
    """Детальная страница прозаического произведения."""
    work = _find_item(PIECES, work_id)
    if work is None:
        abort(404)
    previous, following = _neighbors(PIECES, work)
    return render_template('work_detail.html', active='prose', title=work['title'],
                           work=work, body_html=Markup(work_body_html(work)),
                           section_name='Проза', list_url='/prose/', back_text='Ко всей прозе',
                           detail_prefix='/piece/', previous=previous, following=following,
                           total=len(PIECES))


@app.route('/article/<int:work_id>/')
def article_detail(work_id):
    """Детальная страница статьи."""
    work = _find_item(ARTICLES, work_id)
    if work is None:
        abort(404)
    previous, following = _neighbors(ARTICLES, work)
    return render_template('work_detail.html', active='articles', title=work['title'],
                           work=work, body_html=Markup(work_body_html(work)),
                           section_name='Статьи', list_url='/pieces/', back_text='Ко всем статьям',
                           detail_prefix='/article/', previous=previous, following=following,
                           total=len(ARTICLES))


@app.route('/search/')
def search():
    """Поиск по сборнику."""
    query = (request.args.get('q') or '').strip()
    poem_hits, piece_hits = [], []
    if query:
        needle = query.casefold()
        poem_hits = [work for work in POEMS if needle in work_search_text(work)]
        piece_hits = [work for work in PIECES if needle in work_search_text(work)]
    return render_template('search.html', active='', title='Поиск',
                           description='Поиск по литературному сборнику',
                           query=query, poems=poem_hits, pieces=piece_hits,
                           total=len(poem_hits) + len(piece_hits))


@app.route('/contact/', methods=['GET', 'POST'])
def contact():
    """Страница контактов."""
    sent, name = False, ''
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        sent = bool(name or request.form.get('email') or request.form.get('message'))
    return render_template('contact.html', active='contact', title='Контакты',
                           description='Контактная информация', sent=sent, name=name)


IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}


def _gallery_images():
    """Список URL картинок из static/images, исключая подпапку covers."""
    base = os.path.join(BASE_DIR, 'static', 'images')
    if not os.path.isdir(base):
        return []
    urls = []
    for entry in sorted(os.listdir(base), key=_cased):
        full = os.path.join(base, entry)
        # Пропускаем подпапки (например, covers) — берём только файлы верхнего уровня.
        if os.path.isdir(full):
            continue
        ext = os.path.splitext(entry)[1].lower()
        if ext not in IMAGE_EXTS:
            continue
        urls.append('/static/images/' + entry)
    return urls


@app.route('/static/images/content/<path:filename>')
def obsidian_content_images(filename):
    """Отдаёт картинки, вложенные Obsidian в md_output/static/images/content."""
    content_dir = os.path.join(MD_OUTPUT_DIR, 'static', 'images', 'content')
    return send_from_directory(content_dir, filename)


@app.route('/gallery/')
def gallery():
    """Страница галереи (слайдшоу по картинкам из static/images)."""
    images = _gallery_images()
    return render_template('gallery.html', active='gallery', title='Галерея',
                           description='Галерея иллюстраций и оформления',
                           images=images)


DOWNLOAD_DIR = os.path.join(MD_OUTPUT_DIR, 'download')


def _download_items():
    """Список файлов из md_output/download (рекурсивно) для страницы скачивания."""
    items = []
    if not os.path.isdir(DOWNLOAD_DIR):
        return items
    for dirpath, dirnames, filenames in os.walk(DOWNLOAD_DIR):
        dirnames.sort(key=_cased)
        for filename in sorted(filenames, key=_cased):
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, DOWNLOAD_DIR)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            items.append({
                'path': rel.replace(os.sep, '/'),
                'display': rel.replace(os.sep, ' → '),
                'size': size,
            })
    items.sort(key=lambda item: _cased(item['display']))
    return items


@app.route('/download/')
def downloads():
    """Страница загрузки файлов сборника (из md_output/download)."""
    files = _download_items()
    return render_template('download.html', active='download', title='Скачать',
                           description='Загрузка файлов сборника',
                           files=files)


@app.route('/download/<path:filename>')
def download_file(filename):
    """Отдаёт файл из md_output/download (защита от обхода каталога)."""
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


@app.route('/download/all/')
def download_all():
    """Скачать все файлы из md_output/download одним ZIP-архивом."""
    buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        if os.path.isdir(DOWNLOAD_DIR):
            for dirpath, dirnames, filenames in os.walk(DOWNLOAD_DIR):
                dirnames.sort(key=_cased)
                for filename in sorted(filenames, key=_cased):
                    full = os.path.join(dirpath, filename)
                    rel = os.path.relpath(full, DOWNLOAD_DIR).replace(os.sep, '/')
                    zf.write(full, rel)
                    count += 1
    if count == 0:
        abort(404)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/zip', as_attachment=True,
                     download_name='Сборник_Эллы_Гогелиани.zip')


# --------------------------------------------------------------------------
# Экспорт всего сборника в EPUB
# --------------------------------------------------------------------------

EPUB_STYLE = '''\
body { font-family: Georgia, 'Times New Roman', serif; line-height: 1.6; }
h1 { text-align: center; font-size: 1.5em; margin: 0 0 1em; }
.work-title { text-align: center; font-weight: bold; font-size: 1.3em; margin: 0 0 0.6em; }
.author { text-align: center; font-style: italic; margin: 0 0 1.2em; }
p { text-indent: 1.5em; margin: 0 0 0.6em; }
p.center { text-indent: 0; text-align: center; }
blockquote, td { page-break-inside: avoid; }
'''

EPUB_EPUBS = None  # кэш сгенерированной книги и метки содержимого


def _epub_assembled():
    """Собирает главы, оглавление и content.opf; возвращает набор фрагментов."""
    uid = str(uuid.uuid4())
    modified = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    book_title = 'Жила-была я… Сборник Эллы Гогелиани'
    book_author = 'Элла Гогелиани'

    chapters = []   # (fname, xhtml)
    toc_entries = []  # (section, [(label, href)])
    index = 0
    for section_label, collection in _epub_sections():
        entries = []
        for work in collection:
            index += 1
            fname = 'ch%04d.xhtml' % index
            title = work['title'] or ('Произведение %d' % index)
            body_html = work_body_html(work)
            xhtml = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru">\n'
                '<head><meta charset="utf-8"/>'
                '<title>%s</title>'
                '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
                '<body>\n'
                '<h1 class="work-title">%s</h1>\n'
                '<p class="author">%s</p>\n'
                '%s\n'
                '</body></html>\n'
            ) % (xml_escape(title), xml_escape(title),
                 xml_escape(work['author'] or ''), body_html)
            chapters.append((fname, xhtml))
            entries.append((title, fname))
        toc_entries.append((section_label, entries))

    container = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:'
        'xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>\n'
    )

    manifest_items = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav"/>',
        '<item id="css" href="style.css" media-type="text/css"/>',
    ]
    manifest_items += [
        '<item id="ch%04d" href="%s" media-type="application/xhtml+xml"/>' % (i, fname)
        for i, (fname, _) in enumerate(chapters, start=1)
    ]
    spine_items = ['<itemref idref="ch%04d"/>' % i for i in range(1, len(chapters) + 1)]

    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="uid" xml:lang="ru">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="uid">urn:uuid:%s</dc:identifier>\n'
        '    <dc:title>%s</dc:title>\n'
        '    <dc:creator id="creator">%s</dc:creator>\n'
        '    <dc:language>ru</dc:language>\n'
        '    <meta property="dcterms:modified">%s</meta>\n'
        '    <meta refines="#creator" property="file-as">Гогелиани, Элла</meta>\n'
        '  </metadata>\n'
        '  <manifest>\n%s\n  </manifest>\n'
        '  <spine>\n%s\n  </spine>\n'
        '</package>\n'
    ) % (uid, xml_escape(book_title), xml_escape(book_author), modified,
         '\n'.join(manifest_items), '\n'.join(spine_items))
    return book_title, chapters, toc_entries, container, opf


def build_epub():
    """Собирает EPUB-файл (байты) со всем сборником. Результат кэшируется."""
    global EPUB_EPUBS
    signature = _epub_modified()
    if EPUB_EPUBS is not None and EPUB_EPUBS[0] == signature:
        return EPUB_EPUBS[1]

    book_title, chapters, toc_entries, container, opf = _epub_assembled()

    # nav.xhtml (EPUB3)
    nav_lines = ['<ol>']
    for section_label, entries in toc_entries:
        nav_lines.append('<li><span class="sec">%s</span><ol>' % xml_escape(section_label))
        for label, fname in entries:
            nav_lines.append('<li><a href="%s">%s</a></li>' % (fname, xml_escape(label)))
        nav_lines.append('</ol></li>')
    nav_lines.append('</ol>')
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ru">\n'
        '<head><title>Оглавление</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
        '<body>\n<h1>Оглавление</h1>\n'
        '<nav epub:type="toc" id="toc">\n%s\n</nav>\n'
        '</body></html>\n'
    ) % '\n'.join(nav_lines)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        zf.writestr('mimetype', 'application/epub+zip',
                    compress_type=zipfile.ZIP_STORED)
        zf.writestr('META-INF/container.xml', container)
        zf.writestr('OEBPS/content.opf', opf)
        zf.writestr('OEBPS/nav.xhtml', nav)
        zf.writestr('OEBPS/style.css', EPUB_STYLE)
        for fname, xhtml in chapters:
            zf.writestr('OEBPS/' + fname, xhtml)
    buffer.seek(0)
    data = buffer.read()

    EPUB_EPUBS = (signature, data)
    return data


@app.route('/download/epub/')
def download_epub():
    """Скачать весь сборник в формате EPUB."""
    data = build_epub()
    return send_file(io.BytesIO(data), mimetype='application/epub+zip',
                     as_attachment=True,
                     download_name='Сборник_Эллы_Гогелиани.epub')


def _epub_sections():
    """Разделы сборника в порядке книги."""
    return [('Поэзия', POEMS), ('Проза', PIECES), ('Статьи', ARTICLES)]


def _epub_modified():
    """Метка для пересборки книги при изменении контента."""
    parts = []
    for base in (POETRY_DIR, PROSE_DIR, ARTICLES_DIR):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort(key=_cased)
            for filename in sorted(filenames, key=_cased):
                if not filename.lower().endswith('.md'):
                    continue
                path = os.path.join(dirpath, filename)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                parts.append((path, stat.st_mtime_ns, stat.st_size))
    return parts


@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html', title='Страница не найдена'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html', title='Внутренняя ошибка сервера'), 500


if __name__ == '__main__':
    import sys
    import os
    
    # Режимы запуска:
    # python app.py                          - обычный HTTP на 5001
    # python app.py https                    - HTTPS на 5001 (самоподписанный)
    # python app.py production               - Production-ready (uWSGI/Gunicorn)
    
    if len(sys.argv) > 1 and sys.argv[1] == 'https':
        # Режим с самоподписанным SSL для тестирования
        print("Запуск в режиме HTTPS (самоподписанный сертификат)...")
        print("ВАЖНО: Браузер будет предупреждать о небезопасном соединении!")
        
        # Создаем временный самоподписанный сертификат, если его нет
        cert_dir = os.path.join(BASE_DIR, 'ssl')
        os.makedirs(cert_dir, exist_ok=True)
        cert_file = os.path.join(cert_dir, 'cert.pem')
        key_file = os.path.join(cert_dir, 'key.pem')
        
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            print("Создаю самоподписанный сертификат...")
            import subprocess
            try:
                # Создаем ключ и сертификат
                subprocess.run([
                    'openssl', 'req', '-x509', '-newkey', 'rsa:4096',
                    '-keyout', key_file, '-out', cert_file,
                    '-days', '365', '-nodes', '-subj', '/CN=localhost'
                ], check=False)
                print(f"Сертификат создан: {cert_file}")
            except Exception as e:
                print(f"Ошибка создания сертификата: {e}")
                print("Запускаю без SSL...")
                app.run(host='0.0.0.0', port=5001, debug=False)
                sys.exit(0)
        
        app.run(host='0.0.0.0', port=5001, debug=False,
                ssl_context=(cert_file, key_file))
        
    elif len(sys.argv) > 1 and sys.argv[1] == 'production':
        # Production-режим для Nginx + uWSGI
        print("Запуск в production-режиме (ожидает проксирование от Nginx)...")
        print("Домен должен быть настроен в Nginx с SSL-терминацией")
        app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
        
    else:
        # Стандартный режим (HTTP)
        print("Запуск в стандартном режиме HTTP...")
        app.run(host='0.0.0.0', port=5001, debug=False)