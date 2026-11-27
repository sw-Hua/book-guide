#!/usr/bin/env python3
"""EPUB → units.json + plan.md

把一本 EPUB 拆成「背景＋原文＋解释」可加工的最小单元。

用法:
    python3 extract.py --epub book.epub --out work/
"""
import argparse
import html
import json
import os
import re
import zipfile

from bs4 import BeautifulSoup, Comment, NavigableString


def collect_blocks(epub_path, skip_titles=()):
    z = zipfile.ZipFile(epub_path)
    # 按 spine 顺序读
    opf = None
    for n in z.namelist():
        if n.endswith('.opf'):
            opf = n
            break
    order = []
    if opf:
        s = z.read(opf).decode('utf-8', 'ignore')
        ids = re.findall(r'<item\s+id="([^"]+)"[^>]*href="([^"]+\.x?html?)"', s)
        base = os.path.dirname(opf)
        spine = re.findall(r'<itemref\s+idref="([^"]+)"', s)
        m = dict(ids)
        for sid in spine:
            if sid in m:
                order.append(os.path.normpath(os.path.join(base, m[sid])))
    if not order:
        order = sorted(n for n in z.namelist() if n.endswith(('.xhtml', '.html', '.htm')))

    blocks = []

    def emit(tag, typ, cls, text):
        if text.strip():
            blocks.append({'file': tag, 'type': typ, 'cls': cls, 'text': text.strip()})

    def walk(node, tag):
        for el in list(node.children):
            if isinstance(el, Comment):
                continue
            if isinstance(el, NavigableString):
                t = str(el).strip()
                if t:
                    if t.startswith('<'):
                        inner = BeautifulSoup(t, 'html.parser')
                        if inner.body:
                            walk(inner.body, tag)
                    else:
                        emit(tag, 'p', '', t)
                continue
            name = el.name
            if name in ('script', 'style', 'hr', 'img'):
                continue
            if name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                t = el.get_text().strip()
                if t:
                    emit(tag, name, ' '.join(el.get('class', [])), t)
                continue
            if name == 'p':
                emit(tag, 'p', ' '.join(el.get('class', [])), el.get_text())
                continue
            if name == 'blockquote':
                for p in el.find_all('p'):
                    emit(tag, 'quote', '', p.get_text())
                if not el.find('p'):
                    emit(tag, 'quote', '', el.get_text())
                continue
            if name == 'div':
                cls = ' '.join(el.get('class', []))
                if 'footnote' in cls or 'fnote' in cls or 'note' in cls:
                    t = el.get_text().strip().lstrip('[1]').strip()
                    if t:
                        emit(tag, 'note', '', t)
                    continue
                if el.find('img') and not el.find('p'):
                    cap = el.get_text().strip()
                    if cap:
                        emit(tag, 'caption', '', cap)
                    continue
                walk(el, tag)
                continue
            walk(el, tag) if hasattr(el, 'children') else None

    for f in order:
        try:
            raw = z.read(f).decode('utf-8', 'ignore')
        except KeyError:
            continue
        soup = BeautifulSoup(raw, 'html.parser')
        body = soup.body or soup
        walk(body, f)

    # 去掉封面页与纯版权页
    if blocks:
        out = []
        for b in blocks:
            if any(k in b['text'] for k in skip_titles):
                continue
            out.append(b)
        blocks = out
    return blocks


def is_pseudo_heading(b):
    """译文里常见：p 带 heiti/bold class 且很短，其实是小标题。"""
    cls = b.get('cls', '')
    t = b['text']
    return (b['type'] == 'p' and ('heiti' in cls or 'bold' in cls)
            and len(t) < 24 and t[-1] not in '。！？；')


def segment(blocks, low=620, high=1250, min_unit=380):
    clusters = []
    cur = {'ch': None, 'sec': None, 'body': []}
    for i, b in enumerate(blocks):
        if b['type'] in ('h1', 'h2'):
            if cur['body']:
                clusters.append(cur)
            cur = {'ch': b['text'], 'sec': None, 'body': [i]}
            continue
        if b['type'] in ('h3', 'h4') or is_pseudo_heading(b):
            if cur['body']:
                clusters.append(cur)
            cur = {'ch': cur['ch'], 'sec': b['text'], 'body': [i]}
            continue
        cur['body'].append(i)
    if cur['body']:
        clusters.append(cur)

    units = []
    for c in clusters:
        n = sum(len(blocks[i]['text']) for i in c['body'])
        if n <= high:
            units.append(c)
            continue
        buf, size = [], 0
        for i in c['body']:
            buf.append(i)
            size += len(blocks[i]['text'])
            if size >= low:
                units.append({**c, 'body': buf})
                buf, size = [], 0
        if buf:
            units.append({**c, 'body': buf})

    merged = []
    for u in units:
        n = sum(len(blocks[i]['text']) for i in u['body'])
        if (merged and n < min_unit and merged[-1]['ch'] == u['ch']
                and sum(len(blocks[i]['text']) for i in merged[-1]['body']) + n <= high):
            merged[-1]['body'] += u['body']
            continue
        merged.append(u)

    for n, u in enumerate(merged):
        u['id'] = f'u{n:03d}'
        u['start'] = blocks[u['body'][0]]['type'] in ('h1', 'h2', 'h3', 'h4') or is_pseudo_heading(blocks[u['body'][0]])
        u['chars'] = sum(len(blocks[i]['text']) for i in u['body'])
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epub', required=True)
    ap.add_argument('--out', default='work')
    ap.add_argument('--low', type=int, default=620)
    ap.add_argument('--high', type=int, default=1250)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    blocks = collect_blocks(args.epub)
    units = segment(blocks, args.low, args.high)

    json.dump({'blocks': blocks, 'units': units},
              open(os.path.join(args.out, 'units.json'), 'w'),
              ensure_ascii=False, indent=1)

    with open(os.path.join(args.out, 'plan.md'), 'w') as f:
        for u in units:
            f.write(f"\n### {u['id']} | {u['ch']} | {u['sec']} | {u['chars']} 字\n")
            for i in u['body']:
                b = blocks[i]
                f.write(f"[{b['type']}] {b['text']}\n")

    total = sum(u['chars'] for u in units)
    print(f'units: {len(units)}  chars: {total}')
    print(f'max {max(u["chars"] for u in units)}  min {min(u["chars"] for u in units)}')
    print(f'-> {args.out}/units.json, {args.out}/plan.md')


if __name__ == '__main__':
    main()
