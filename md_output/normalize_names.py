import os
import re

import yaml

# Папки, которые нужно обработать (относительно корня проекта)
DIRS = ['md_output/поэзия', 'md_output/проза', 'md_output/статьи']

# Запрещенные символы для Windows
INVALID_CHARS = r'[\\/*?:"<>|]'
FRONTMATTER_RE = re.compile(r'\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)\Z', re.DOTALL)

def clean_name(name):
    """Очищает строку и делает её красивой (Каждое Слово С Заглавной Буквы)."""
    # Убираем расширение .md, если оно есть
    if name.lower().endswith('.md'):
        name = name[:-3]
    
    # Заменяем подчеркивания и дефисы на пробелы
    name = name.replace('_', ' ').replace('-', ' ')
    
    # Удаляем запрещенные символы
    name = re.sub(INVALID_CHARS, '', name)
    
    # Убираем двойные пробелы
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Делаем каждое слово с большой буквы, остальные строчными
    if name:
        name = name.title()
        
    return name

def process_directory(dir_path):
    # Проходим по папкам снизу вверх, чтобы переименование папок не ломало пути
    for root, dirs, files in os.walk(dir_path, topdown=False):
        
        # 1. Обрабатываем файлы
        for filename in files:
            if not filename.endswith('.md'):
                continue
                
            filepath = os.path.join(root, filename)
            
            # Читаем файл
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            match = FRONTMATTER_RE.match(content)
            new_name = clean_name(filename)
            
            if match:
                meta_text, body = match.group(1), match.group(2)
                try:
                    meta = yaml.safe_load(meta_text) or {}
                except yaml.YAMLError:
                    meta = {}
                
                # Обновляем title
                meta['title'] = new_name
                
                # Собираем файл обратно
                new_meta_text = yaml.dump(meta, allow_unicode=True, sort_keys=False).strip()
                new_content = f"---\n{new_meta_text}\n---\n{body.lstrip()}"
            else:
                new_content = content
                
            # Записываем обновленный контент
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            # Переименовываем сам файл
            new_filepath = os.path.join(root, new_name + '.md')
            if filepath != new_filepath:
                try:
                    os.rename(filepath, new_filepath)
                    print(f"Файл: {filename} -> {new_name}.md")
                except OSError as e:
                    print(f"Ошибка переименования файла {filename}: {e}")

        # 2. Обрабатываем папки (снизу вверх)
        for dirname in dirs:
            new_dirname = clean_name(dirname)
            old_dirpath = os.path.join(root, dirname)
            new_dirpath = os.path.join(root, new_dirname)
            
            if old_dirpath != new_dirpath:
                try:
                    os.rename(old_dirpath, new_dirpath)
                    print(f"Папка: {dirname} -> {new_dirname}")
                except OSError as e:
                    print(f"Ошибка переименования папки {dirname}: {e}")

if __name__ == '__main__':
    print("Начинаем нормализацию названий...")
    for d in DIRS:
        if os.path.exists(d):
            process_directory(d)
    print("Готово!")
    