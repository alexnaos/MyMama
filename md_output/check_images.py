import os
import re

MD_DIR = 'md_output'
CONTENT_DIR = os.path.join(MD_DIR, 'static', 'images', 'content')
# Регулярка ищет и ![[...]], и ![...](...)
IMG_RE = re.compile(r'(!\[\[|\!\[.*?\]\()([^\]\)]+)')

def check_links():
    broken = []
    for root, _, files in os.walk(MD_DIR):
        for f in files:
            if not f.endswith('.md'): continue
            filepath = os.path.join(root, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                text = file.read()
                
            matches = IMG_RE.findall(text)
            for prefix, path in matches:
                path = path.strip()
                # Если путь ведет в папку content, проверяем его
                if 'static/images/content' in path:
                    # Очищаем путь от возможных размеров |300
                    if '|' in path: path = path.split('|')[0]
                    
                    # Строим полный путь
                    full_path = os.path.join(os.getcwd(), path.replace('/static/', 'md_output/static/'))
                    # Если файла нет, добавляем в список битых
                    if not os.path.exists(full_path):
                        broken.append(f"Файл {f}: не найдена картинка {path}")

    if broken:
        print("НАЙДЕНЫ БИТЫЕ ССЫЛКИ:")
        for b in broken:
            print(b)
    else:
        print("Все ссылки корректны!")

if __name__ == '__main__':
    check_links()