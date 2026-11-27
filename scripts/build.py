#!/usr/bin/env python3
"""units.json + anno/*.json → 导读版 EPUB + 朗读稿 TXT

用法:
    python3 build.py --units work/units.json --anno work/anno \
        --out "书名_导读版.epub" --txt "书名_朗读稿.txt" --title "书名（导读版）"

anno 目录下每个 json 形如:
    {"u012": {"bg": "……", "ex": "……"}}
"""
import argparse
import glob
import html
import json
import os
import re
import shutil
import zipfile

CSS = """@charset "utf-8";
body{font-family:serif;line-height:1.75;margin:0 6%;color:#1a1a1a;}
h1{font-size:1.6em;font-weight:normal;margin:2.2em 0 1.2em;text-align:left;border-bottom:2px solid #2b2b2b;padding-bottom:.4em;}
h2{font-size:1.45em;font-weight:normal;margin:2em 0 1em;border-bottom:1px solid #888;padding-bottom:.3em;}
h3{font-size:1.35em;font-weight:bold;margin:2.4em 0 .8em;}
h4{font-size:1.1em;font-weight:bold;margin:1.6em 0 .5em;}
p{margin:.55em 0;text-indent:2em;text-align:justify;}
p.noind,p.lab{text-indent:0;}
p.center{text-align:center;text-indent:0;}
blockquote{margin:1em 1.6em;}
blockquote p{text-indent:0;}
div.bg,div.ex{margin:1em 0;padding:.7em .9em;border-left:3px solid #999;background:#f4f4f4;}
div.bg p,div.ex p{text-indent:0;font-size:.95em;}
div.bg{border-left-color:#7a8b7a;}
div.ex{border-left-color:#8b7a6a;}
p.lab{font-size:.78em;letter-spacing:.3em;color:#666;margin-bottom:.35em;}
p.fnote{font-size:.82em;color:#555;text-indent:0;margin-top:.8em;}
div.img{text-align:center;margin:1em 0;}
div.img img{max-width:100%;}
p.imgcap{text-align:center;text-indent:0;font-size:.85em;color:#555;}
div.unit{margin-bottom:2.6em;}
"""

XHEAD = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
<title>{t}</title>
<link rel="stylesheet" type="text/css" href="../Styles/main.css"/>
</head>
<body>
'''


def esc(t):
    return html.escape(t, quote=False)


def para(b):
    t = esc(b['text'])
    if b['type'] == 'quote':
        return f'<blockquote><p>{t}</p></blockquote>'
    if b['type'] == 'note':
        return f'<p class="fnote">{t}</p>'
    if b['type'] == 'caption':
        return f'<p class="imgcap">{t}</p>'
    return '<p class="center">%s</p>' % t if 'center' in b.get('cls', '') else f'<p>{t}</p>'


def unit_xml(u, blocks, anno):
    out = ['<div class="unit">']
    for i in u['body']:
        if blocks[i]['type'] in ('h4', 'h5'):
            out.append(f'<h4>{esc(blocks[i]["text"])}</h4>')
            break
    a = anno.get(u['id'], {})
    if a.get('bg'):
        out.append(f'<div class="bg"><p class="lab">背景</p><p>{esc(a["bg"])}</p></div>')
    out.append('<div class="src">')
    for i in u['body']:
        b = blocks[i]
        if b['type'] in ('h1', 'h2', 'h3', 'h4', 'h5'):
            continue
        if re.match(r'^p$', b['type']) and len(b['text']) < 24 and b['text'][-1:] not in '。！？；':
            out.append(f'<p class="noind"><b>{esc(b["text"])}</b></p>')
            continue
        out.append(para(b))
    out.append('</div>')
    if a.get('ex'):
        out.append(f'<div class="ex"><p class="lab">解释</p><p>{esc(a["ex"])}</p></div>')
    out.append('</div>')
    return '\n'.join(out)


def write_epub(chapters, images, out_path, title):
    root = os.path.join('__epub_tmp__')
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(os.path.join(root, 'OEBPS/Text'))
    os.makedirs(os.path.join(root, 'OEBPS/Styles'))
    os.makedirs(os.path.join(root, 'OEBPS/Images'))
    os.makedirs(os.path.join(root, 'META-INF'))

    open(os.path.join(root, 'OEBPS/Styles/main.css'), 'w').write(CSS)
    for name, xml in chapters:
        open(os.path.join(root, 'OEBPS/Text', name), 'w').write(xml)
    for name, data in images.items():
        open(os.path.join(root, 'OEBPS/Images', name), 'wb').write(data)

    manifest = ['<item id="css" href="Styles/main.css" media-type="text/css"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>']
    spine = []
    for name, _ in chapters:
        iid = name.replace('.xhtml', '')
        manifest.append(f'<item id="{iid}" href="Text/{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{iid}"/>')
    for name in images:
        manifest.append(f'<item id="im_{name.replace(".", "_")}" href="Images/{name}" media-type="image/jpeg"/>')

    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{esc(title)}</dc:title>
    <dc:language>zh-CN</dc:language>
    <dc:identifier id="BookId">urn:uuid:{__import__("uuid").uuid4()}</dc:identifier>
  </metadata>
  <manifest>
    {chr(10).join(manifest)}
  </manifest>
  <spine toc="ncx">
    {chr(10).join(spine)}
  </spine>
</package>
'''
    open(os.path.join(root, 'OEBPS/content.opf'), 'w').write(opf)

    nav = []
    for n, (name, xml) in enumerate(chapters, 1):
        m = re.search(r'<h[123]>(.*?)</h[123]>', xml)
        t = html.unescape(re.sub('<[^>]+>', '', m.group(1))) if m else name
        nav.append(f'''    <navPoint id="np{n}" playOrder="{n}">
      <navLabel><text>{html.escape(t)}</text></navLabel>
      <content src="Text/{name}"/>
    </navPoint>''')
    ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="book-guide"/></head>
  <docTitle><text>{esc(title)}</text></docTitle>
  <navMap>
{chr(10).join(nav)}
  </navMap>
</ncx>
'''
    open(os.path.join(root, 'OEBPS/toc.ncx'), 'w').write(ncx)
    open(os.path.join(root, 'META-INF/container.xml'), 'w').write('''<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
''')

    if os.path.exists(out_path):
        os.remove(out_path)
    z = zipfile.ZipFile(out_path, 'w')
    z.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
    for dirpath, _, fns in os.walk(root):
        for fn in fns:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            z.write(full, rel, compress_type=zipfile.ZIP_DEFLATED)
    z.close()
    shutil.rmtree(root)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--units', required=True)
    ap.add_argument('--anno', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--txt', default=None)
    ap.add_argument('--title', default='导读版')
    ap.add_argument('--epub', default=None, help='原书 epub，用于抽取图片')
    args = ap.parse_args()

    M = json.load(open(args.units))
    blocks, units = M['blocks'], M['units']

    anno = {}
    for f in sorted(glob.glob(os.path.join(args.anno, '*.json'))):
        anno.update(json.load(open(f)))

    chapters, cur = [], None
    for u in units:
        head = blocks[u['body'][0]]
        if head['type'] in ('h1', 'h2', 'h3') or cur is None:
            cur = {'title': head['text'],
                   'tag': 'h1' if head['type'] in ('h1', 'h2') else 'h3',
                   'units': []}
            chapters.append(cur)
        cur['units'].append(u)

    files = []
    for n, ch in enumerate(chapters):
        parts = [XHEAD.format(t=esc(ch['title']))]
        parts.append(f'<{ch["tag"]}>{esc(ch["title"])}</{ch["tag"]}>')
        for u in ch['units']:
            parts.append(unit_xml(u, blocks, anno))
        parts.append('\n</body>\n</html>\n')
        files.append((f'c{n:02d}.xhtml', ''.join(parts)))

    images = {}
    if args.epub and os.path.exists(args.epub):
        z = zipfile.ZipFile(args.epub)
        for n in z.namelist():
            if '/Images/' in n or n.lower().endswith(('.jpg', '.jpeg', '.png')):
                images[os.path.basename(n)] = z.read(n)

    write_epub(files, images, args.out, args.title)
    print(f'epub -> {args.out}  ({len(files)} chapters, {len(anno)} units annotated)')

    if args.txt:
        # 修补被拆开的段落
        drop = set()
        for i in range(1, len(blocks)):
            a, b = blocks[i - 1], blocks[i]
            if a['type'] == 'p' and b['type'] == 'p' and len(b['text']) <= 3:
                a['text'] = a['text'].strip() + b['text'].strip()
                drop.add(i)
        out = []
        for u in units:
            body = [i for i in u['body'] if i not in drop]
            for i in body:
                if blocks[i]['type'] in ('h1', 'h2', 'h3', 'h4', 'h5'):
                    out.append('')
                    out.append(f'【{blocks[i]["text"]}】')
            a = anno.get(u['id'], {})
            if a.get('bg'):
                out.append('【背景】' + a['bg'])
            out.append('【原文】')
            for i in body:
                if blocks[i]['type'] not in ('h1', 'h2', 'h3', 'h4', 'h5') and blocks[i]['text'].strip():
                    out.append(blocks[i]['text'].strip())
            if a.get('ex'):
                out.append('【解释】' + a['ex'])
        txt = re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip() + '\n'
        open(args.txt, 'w').write(txt)
        print(f'txt  -> {args.txt}  ({len(txt)} chars)')


if __name__ == '__main__':
    main()
