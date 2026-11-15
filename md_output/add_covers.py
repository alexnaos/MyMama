import glob
import os
import random
import re

# Надежное определение корня проекта: 
# Если скрипт лежит в md_output, поднимаемся на уровень выше
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(BASE_DIR) == 'md_output':
    BASE_DIR = os.path.dirname(BASE_DIR)

MD_OUTPUT_DIR = os.path.join(BASE_DIR, 'md_output')

# Папки с текстами
DIRS = [
    os.path.join(MD_OUTPUT_DIR, 'поэзия'),
    os.path.join(MD_OUTPUT_DIR, 'проза'),
    os.path.join(MD_OUTPUT_DIR, 'статьи')
]

# Папка с картинками
COVERS_DIR = os.path.join(BASE_DIR, 'static', 'images', 'covers')

# Сканируем картинки
valid_images = []
if os.path.exists(COVERS_DIR):
    valid_images = [f for f in os.listdir(COVERS_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
else:
    print(f"ВНИМАНИЕ: Папка с картинками не найдена по пути: {COVERS_DIR}")
    print("Убедитесь, что вы создали папку static/images/covers в корне проекта и положили туда картинки.")

if not valid_images:
    print("ВНИМАНИЕ: В папке covers нет картинок!")

# Регулярное выражение для поиска YAML-заголовка
FRONTMATTER_RE = re.compile(r'\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)\Z', re.DOTALL)

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    match = FRONTMATTER_RE.match(content)
    if not match:
        return False

    meta_text, body = match.group(1), match.group(2)
    meta_lines = meta_text.splitlines()
    
    has_publish = any(re.match(r'^publish\s*:', line, re.IGNORECASE) for line in meta_lines)
    has_cover = any(re.match(r'^cover\s*:', line, re.IGNORECASE) for line in meta_lines)

    new_lines = []
    
    if not has_publish:
        new_lines.append('publish: true')
        
    if not has_cover and valid_images:
        chosen_img = random.choice(valid_images)
        digits = re.search(r'\d+', chosen_img)
        cover_val = digits.group() if digits else chosen_img
        new_lines.append(f"cover: '{cover_val}'")

    if not new_lines:
        return False

    new_meta_text = '\n'.join(meta_lines + new_lines)
    new_content = f"---\n{new_meta_text}\n---\n{body.lstrip()}"

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return True

if __name__ == '__main__':
    print("="*40)
    print("Безопасное добавление полей...")
    print(f"Корень проекта определен как: {BASE_DIR}")
    print("="*40)
    
    count_total = 0
    count_changed = 0
    
    for folder in DIRS:
        if not os.path.exists(folder): 
            print(f"Папка не найдена: {folder}")
            continue
            
        print(f"Сканирую: {os.path.basename(folder)}...")
        for filepath in glob.glob(os.path.join(folder, '**/*.md'), recursive=True):
            count_total += 1
            if process_file(filepath):
                count_changed += 1
                
    print("\n" + "="*40)
    print(f"Готово! Всего найдено заметок: {count_total}")
    print(f"Изменено (добавлены поля): {count_changed}")
    print("="*40)