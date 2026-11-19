#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Присваивает каждой заметке порядковый номер:
  - пишет номер в поле cover: 'N' в YAML front matter
  - вставляет картинку ![SOimageN](static/images/content/SOimageN.jpg)
    в начало заметки (сразу после front matter)
  - удаляет старые вставки картинок из папки content
По умолчанию работает в режиме предпросмотра (dry-run).
"""

import argparse
import os
import pathlib
import re
import sys

BASE_DIR = r'C:\Projects\MyMama'
CONTENT_IMG_RE = re.compile(r'!\[[^\]]*\]\([^)]*static/images/content[^)]*\)')
FRONTMATTER_RE = re.compile(
    r'\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?', re.DOTALL
)


def assign_number(filepath, number):
    """
    Присваивает файлу порядковый номер:
      - обновляет cover: 'N' в front matter
      - удаляет старую картинку content из тела
      - вставляет ![SOimageN](static/images/content/SOimageN.jpg) после front matter
    """
    text = filepath.read_text(encoding='utf-8')
    fm_match = FRONTMATTER_RE.match(text)

    if fm_match:
        meta_text = fm_match.group(1)
        body = text[fm_match.end():]

        # Обновляем cover в метаданных
        new_meta_lines = []
        cover_updated = False
        for line in meta_text.splitlines():
            if re.match(r'^cover\s*:', line, re.IGNORECASE):
                new_meta_lines.append(f"cover: '{number}'")
                cover_updated = True
            else:
                new_meta_lines.append(line)
        if not cover_updated:
            new_meta_lines.append(f"cover: '{number}'")

        new_meta_text = '\n'.join(new_meta_lines)
    else:
        new_meta_text = f"cover: '{number}'\ntitle: {filepath.stem}"
        body = text

    # Удаляем все старые картинки content из тела
    body_cleaned = CONTENT_IMG_RE.sub('', body)
    body_cleaned = re.sub(r'\n{3,}', '\n\n', body_cleaned).lstrip('\n\r')

    # Новая картинка по порядковому номеру
    img_tag = f"![SOimage{number}](static/images/content/SOimage{number}.jpg)"

    if fm_match:
        new_text = f"---\n{new_meta_text}\n---\n{img_tag}\n\n{body_cleaned}"
    else:
        new_text = f"---\n{new_meta_text}\n---\n{img_tag}\n\n{body}"

    return new_text, new_text != text


def process_folder(md_folder, apply=False, start_number=1):
    md_folder_path = pathlib.Path(md_folder)
    md_files = sorted(
        md_folder_path.rglob('*.md'),
        key=lambda p: str(p).lower()
    )

    counter = start_number
    stats = {'total': 0, 'changed': 0, 'skipped': 0}

    for filepath in md_files:
        stats['total'] += 1
        try:
            new_text, changed = assign_number(filepath, counter)
        except Exception as e:
            print(f"[ОШИБКА] {filepath}: {e}")
            stats['skipped'] += 1
            counter += 1
            continue

        if changed:
            stats['changed'] += 1
            print(f"[ОК] {filepath.name} -> cover: '{counter}', картинка SOimage{counter}.jpg")
            if apply:
                filepath.write_text(new_text, encoding='utf-8')
        else:
            stats['skipped'] += 1
            print(f"[ПРОПУСТ] {filepath.name} (уже имеет номер {counter})")

        counter += 1

    return stats, counter - 1


def main():
    parser = argparse.ArgumentParser(
        description="Присваивает каждой заметке порядковый номер и картинку SOimageN.jpg."
    )
    parser.add_argument(
        'md_folder',
        nargs='?',
        default=os.path.join(BASE_DIR, 'md_output'),
        help="Папка с .md заметками",
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help="Реально изменить файлы. Без ключа — только предпросмотр.",
    )
    parser.add_argument(
        '--start',
        type=int,
        default=1,
        help="Начальный порядковый номер (по умолчанию 1).",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.md_folder):
        print(f"Ошибка: папка не найдена: {args.md_folder}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("РЕЖИМ: ПРЕДПРОСМОТР (ничего не меняется)" if not args.apply else "РЕЖИМ: ПРИМЕНЕНИЕ ИЗМЕНЕНИЙ")
    print(f"Папка: {args.md_folder}")
    print(f"Начальный номер: {args.start}")
    print("=" * 60)

    stats, last_number = process_folder(args.md_folder, apply=args.apply, start_number=args.start)

    print("\n" + "=" * 60)
    print("ИТОГ:")
    print(f"  Всего .md-файлов:     {stats['total']}")
    print(f"  Изменено:             {stats['changed']}")
    print(f"  Пропущено:            {stats['skipped']}")
    print(f"  Последний номер:      {last_number}")
    print("=" * 60)

    if not args.apply:
        print("\nЧтобы применить изменения, запустите с ключом --apply.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
