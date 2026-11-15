"""
Литературный сборник — онлайн-архив поэзии и прозы Эллы Гогелиани.

Flask-приложение загружает markdown-файлы из каталогов
md_output/поэзия и md_output/проза (включая вложенные папки),
читает YAML-front matter (title, author, created, description, tags)
и отображает произведения: списки, детальные страницы и поиск.

Весь контент хранится в кодировке UTF-8 — кириллица поддерживается полностью.
"""

import os
import re
import time

import markdown as mdlib
import yaml
from flask import Flask, abort, render_template, request
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


def _excerpt_source(text, limit=240):
    """Краткая выжимка чистого текста."""
    clean = _strip_html(text)
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
        'folder': folder,
        'folder_label': folder_label,
        'path': path,
        'raw_body': raw_body,
        '_html_cache': None,
        '_excerpt_cache': None,
        '_search_cache': None,
    }


def render_markdown(text):
    """Рендерит markdown в HTML."""
    return mdlib.markdown(text, extensions=MARKDOWN_EXTENSIONS)


def work_body_html(work):
    """HTML-версия тела произведения (рендерится один раз и кэшируется)."""
    if work['_html_cache'] is None:
        html = render_markdown(work['raw_body']).strip()
        work['_html_cache'] = html or work['raw_body']
    return work['_html_cache']


def work_excerpt(work, limit=240):
    """Краткая выжимка текста для карточки произведения."""
    if work['_excerpt_cache'] is None:
        source = work['description'] or work['raw_body']
        work['_excerpt_cache'] = _excerpt_source(source, limit)
    return work['_excerpt_cache']


def work_search_text(work):
    """Нормализованный текст для поиска по сборнику."""
    if work['_search_cache'] is None:
        parts = [work['title'], work['author'], work['description'],
                 _strip_html(work['raw_body'])]
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
    """Функции, доступные во всех шаблонах."""
    return {'work_excerpt': work_excerpt,
            'work_body_html': work_body_html,
            'ru_plural': ru_plural}
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


@app.route('/gallery/')
def gallery():
    """Страница галереи."""
    return render_template('gallery.html', active='gallery', title='Галерея',
                           description='Галерея иллюстраций и оформления')


@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html', title='Страница не найдена'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html', title='Внутренняя ошибка сервера'), 500


if __name__ == '__main__':
    import os
    import socket
    import sys
    import threading
    import webbrowser

    host = '0.0.0.0'
    port = 5000
    if '--port' in sys.argv:
        port = int(sys.argv[sys.argv.index('--port') + 1])

    # Порт 5000 может быть занят (например, зависшим процессом) —
    # автоматически подбираем ближайший свободный порт.
    chosen = port
    is_reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if not is_reloader_child:
        for candidate in range(port, port + 20):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind((host, candidate))
                sock.close()
                chosen = candidate
                break
            except OSError:
                sock.close()
        url = f'http://{host}:{chosen}/'
        print('=' * 60)
        print('  Элла')
        print(f'  Откройте в браузере: {url}')
        print('  Остановка: Ctrl+C')
        print('=' * 60)
        if '--no-browser' not in sys.argv:
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(debug=True, host=host, port=chosen)