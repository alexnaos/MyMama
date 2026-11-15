# -*- coding: utf-8 -*-
"""Самопроверка проекта: рендер всех markdown-файлов и обход всех маршрутов."""
import io
import traceback

import app as app_module

report = io.StringIO()


# 1) Рендер всех произведений
def check_render(collections):
    errors = []
    for collection in collections:
        for work in collection:
            try:
                app_module.work_body_html(work)
            except Exception as exc:  # noqa: BLE001
                errors.append((work['path'], repr(exc)))
    return errors


render_errors = check_render([app_module.POEMS, app_module.PIECES])
report.write(f"Всего стихотворений: {len(app_module.POEMS)}\n")
report.write(f"Всего произведений прозы: {len(app_module.PIECES)}\n")
report.write(f"Ошибок рендера markdown: {len(render_errors)}\n")
for path, err in render_errors:
    report.write(f"  ОШИБКА: {path} — {err}\n")


# 2) Обход маршрутов
client = app_module.app.test_client()
routes = [
    ('/', {}),
    ('/poetry/', {}),
    ('/prose/', {}),
    ('/about/', {}),
    ('/contact/', {}),
    ('/gallery/', {}),
    ('/search/?q=любовь', {}),
    ('/search/?q=Элла', {}),
    ('/search/?q=', {}),
    ('/poem/1/', {}),
    ('/poem/%d/' % len(app_module.POEMS), {}),
    ('/piece/1/', {}),
    ('/piece/%d/' % len(app_module.PIECES), {}),
    ('/nonexistent/', {}),
]


def follow(path, method='get', **kwargs):
    try:
        response = getattr(client, method)(path, **kwargs)
        return response.status_code, response
    except Exception as exc:  # noqa: BLE001
        return 'EXC', exc


report.write("\n--- Обход маршрутов ---\n")
failures = 0
for path, _ in routes:
    status, response = follow(path)
    if isinstance(status, int) and 200 <= status < 500:
        report.write(f"OK   {status}  {path}\n")
    else:
        failures += 1
        report.write(f"FAIL {status}  {path}\n")
        if not isinstance(status, int):
            report.write(traceback.format_exc()[:800] + "\n")

# POST /contact/
status, response = follow('/contact/', method='post', data={'name': 'Тест', 'message': 'Привет!'})
report.write(f"{(('OK' if status == 200 else 'FAIL'), status)}  POST /contact/ (форма)\n")

# Сохраняем HTML ключевых страниц для визуальной проверки
samples = {
    'index': '/',
    'poetry': '/poetry/',
    'prose': '/prose/',
    'poem': '/poem/1/',
    'piece': '/piece/1/',
    'search': '/search/?q=любовь',
    'about': '/about/',
    'gallery': '/gallery/',
    'contact': '/contact/',
    '404': '/no-such-page/',
}
for key, path in samples.items():
    response = client.get(path)
    html = response.get_data(as_text=True)
    with open(rf"c:\Projects\MyMama\selftest_{key}.html", 'w', encoding='utf-8') as handle:
        handle.write(html)
report.write("\nHTML-сэмплы сохранены в selftest_*.html\n")

report.write("\nИТОГ: " + ("ВСЁ ОК" if not failures and not render_errors else "ЕСТЬ ПРОБЛЕМЫ") + "\n")
with open(r"c:\Projects\MyMama\selftest_report.txt", 'w', encoding='utf-8') as handle:
    handle.write(report.getvalue())
print("done")