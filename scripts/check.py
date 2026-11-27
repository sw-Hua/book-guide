#!/usr/bin/env python3
"""注解文案质检

用法:
    python3 check.py --anno work/anno/ --units work/units.json
"""
import argparse
import glob
import json
import os
import re

BANNED = ['意味深长', '耐人寻味', '发人深省', '不禁让人', '某种程度上', '不得不说',
          '恰恰', '深刻', '洞见', '底层逻辑', '闭环', '值得玩味', '令人深思',
          '首先，', '其次，', '最后，']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--anno', default='work/anno')
    ap.add_argument('--units', default='work/units.json')
    ap.add_argument('--maxlen', type=int, default=52)
    args = ap.parse_args()

    anno = {}
    for f in sorted(glob.glob(os.path.join(args.anno, '*.json'))):
        anno.update(json.load(open(f)))

    problems = []

    if os.path.exists(args.units):
        M = json.load(open(args.units))
        ids = [u['id'] for u in M['units']]
        missing = [i for i in ids if i not in anno]
        if missing:
            problems.append(f'覆盖率：缺 {len(missing)} 个单元 {missing[:5]}…')
        extra = [i for i in anno if i not in ids]
        if extra:
            problems.append(f'多余：{len(extra)} 个 id 不在 units 中 {extra[:5]}')

    for k, v in anno.items():
        for part in ('bg', 'ex'):
            t = v.get(part, '')
            if not t:
                problems.append(f'{k}.{part} 为空')
                continue
            for w in BANNED:
                if w in t:
                    problems.append(f'{k}.{part} 含禁词「{w}」')
            if '——' in t:
                problems.append(f'{k}.{part} 含破折号')
            if len(t) > 220:
                problems.append(f'{k}.{part} 过长（{len(t)} 字）')
            for s in re.split(r'[。；]', t):
                if len(s) > args.maxlen:
                    problems.append(f'{k}.{part} 长句 {len(s)} 字：{s[:20]}…')

    if problems:
        print(f'发现 {len(problems)} 个问题：')
        for p in problems:
            print('  -', p)
    else:
        print(f'全部通过（{len(anno)} 个单元）')


if __name__ == '__main__':
    main()
