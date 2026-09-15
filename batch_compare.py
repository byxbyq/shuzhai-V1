# -*- coding: utf-8 -*-
"""
批量 AI 对照脚本：为所有有正文但没有 divergences 的章节生成对照结果
"""
import sys
import json
import time
import urllib.request
import urllib.error

BASE_URL = 'http://localhost:8894/api/timeline'

def compare_one(vol_idx, ch_idx):
    url = f'{BASE_URL}/{vol_idx}/{ch_idx}/compare'
    data = json.dumps({}).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')

    try:
        r = urllib.request.urlopen(req, timeout=60)
        d = json.loads(r.read())
        return d.get('ok', False), d.get('msg', '')
    except Exception as e:
        return False, str(e)

def main():
    print('=' * 60)
    print('批量 AI 对照')
    print('=' * 60)

    r = urllib.request.urlopen(f'{BASE_URL}')
    d = json.loads(r.read())
    vols = d.get('timeline', {}).get('volumes', {})

    tasks = []
    for vk in sorted(vols.keys(), key=int):
        chs = vols[vk].get('chapters', {})
        for ck in sorted(chs.keys(), key=int):
            ch = chs[ck]
            info = d.get('chapters', {}).get(ck, {})

            has_content = info.get('has_content', False)
            has_divergences = len(ch.get('divergences', [])) > 0

            if has_content and not has_divergences:
                tasks.append({
                    'vol': int(vk),
                    'ch': int(ck),
                    'title': ch.get('title', '')
                })

    print(f'待对照章节数: {len(tasks)}')

    success_count = 0
    fail_count = 0

    for i, t in enumerate(tasks):
        print(f'\r进度: {i+1}/{len(tasks)} | 成功{success_count} | 失败{fail_count} | 第{t["ch"]}章', end='')

        ok, msg = compare_one(t['vol'], t['ch'])

        if ok:
            success_count += 1
        else:
            fail_count += 1
            print(f'\n  第{t["ch"]}章对照失败: {msg}')

        time.sleep(0.5)

    print()
    print('=' * 60)
    print(f'批量对照完成')
    print(f'  成功: {success_count}')
    print(f'  失败: {fail_count}')
    print('=' * 60)

if __name__ == '__main__':
    main()
