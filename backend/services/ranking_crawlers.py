# -*- coding: utf-8 -*-
"""排行服务扫榜爬虫方法（从 ranking_service.py 拆分）"""
import json, re, logging, datetime
from typing import List, Dict, Optional

from backend.services.ranking_data import (
    PLATFORM_CONFIG, FALLBACK_RANKING, _save_cache, _load_cache,
    _get_headers, _random_delay, extract_json_from_js,
)

logger = logging.getLogger(__name__)


class RankingCrawlerMixin:
    """提供多平台扫榜爬虫方法"""
    # ═══════════════════════════════════════
    # 公共接口
    # ═══════════════════════════════════════

    def get_platform_config(self) -> Dict:
        """获取所有平台配置"""
        return {
            'platforms': PLATFORM_CONFIG,
        }

    def scan_ranking(self, platform: str = 'qidian', rank_type: str = 'hot',
                     category: str = 'all') -> Dict:
        """通用扫榜接口

        Args:
            platform: 平台标识（qidian/fanqie/feilu/jjwxc/qimao/ciweimao/zongheng/qidian_girl）
            rank_type: 榜单类型
            category: 分类

        Returns:
            {'ok': True, 'data': [...], 'source': 'live'/'cache'/'fallback', ...}
        """
        if platform not in PLATFORM_CONFIG:
            return {'ok': False, 'error': f'不支持的平台: {platform}'}

        cache_key = f'{platform}_{rank_type}_{category}'

        # 尝试实时爬取
        try:
            session = self._get_session()
            if session is not None:
                books = self._scan_platform(session, platform, rank_type, category)
                if books:
                    result = {
                        'ok': True,
                        'source': 'live',
                        'platform': platform,
                        'platform_name': PLATFORM_CONFIG[platform]['name'],
                        'rank_type': rank_type,
                        'rank_type_name': PLATFORM_CONFIG[platform]['rank_types'].get(rank_type, rank_type),
                        'category': category,
                        'category_name': PLATFORM_CONFIG[platform]['categories'].get(category, category),
                        'scanned_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'data': books,
                        'total': len(books),
                    }
                    _save_cache(cache_key, result)
                    return result
        except Exception as e:
            logger.warning(f'[扫榜] {platform} 爬取失败: {e}')

        # 尝试缓存
        cached = _load_cache(cache_key)
        if cached:
            cached['source'] = 'cache'
            cached['ok'] = True
            return cached

        # 降级到内置数据
        return self._fallback_result(platform, rank_type, category)

    def _fallback_result(self, platform: str, rank_type: str, category: str) -> Dict:
        """生成降级结果"""
        return {
            'ok': True,
            'source': 'fallback',
            'platform': platform,
            'platform_name': PLATFORM_CONFIG.get(platform, {}).get('name', platform),
            'rank_type': rank_type,
            'rank_type_name': PLATFORM_CONFIG.get(platform, {}).get('rank_types', {}).get(rank_type, rank_type),
            'category': category,
            'category_name': PLATFORM_CONFIG.get(platform, {}).get('categories', {}).get(category, category),
            'scanned_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data': FALLBACK_RANKING,
            'total': len(FALLBACK_RANKING),
            'note': '网络不可用，显示内置参考数据',
        }

    def _scan_platform(self, session, platform: str, rank_type: str, category: str) -> Optional[List[Dict]]:
        """根据平台调用对应的爬取方法"""
        handlers = {
            'qidian': self._scan_qidian,
            'qidian_girl': self._scan_qidian_girl,
            'fanqie': self._scan_fanqie,
            'feilu': self._scan_feilu,
            'jjwxc': self._scan_jjwxc,
            'qimao': self._scan_qimao,
            'ciweimao': self._scan_ciweimao,
            'zongheng': self._scan_zongheng,
        }
        handler = handlers.get(platform)
        if handler:
            return handler(session, rank_type, category)
        return None

    # ═══════════════════════════════════════
    # 1. 起点中文网（用移动版绕过反爬）
    # ═══════════════════════════════════════

    def _scan_qidian(self, session, rank_type: str, category: str) -> Optional[List[Dict]]:
        """爬取起点中文网榜单（移动版绕过反爬）"""
        url_map = {
            'yuepiao': 'https://m.qidian.com/rank/yuepiao',
            'hotsales': 'https://m.qidian.com/rank/hotsales',
            'recommend': 'https://m.qidian.com/rank/recommend',
            'hits': 'https://m.qidian.com/rank/hits',
            'collect': 'https://m.qidian.com/rank/collect',
            'newbook': 'https://m.qidian.com/rank/newbook',
        }
        base_url = url_map.get(rank_type, url_map['hotsales'])

        cat_map = {
            'all': '', 'xuanhuan': 'chanId=21', 'dushi': 'chanId=1', 'xianxia': 'chanId=22',
            'kehuan': 'chanId=2', 'lishi': 'chanId=4', 'youxi': 'chanId=14',
            'qingxiaoshuo': 'chanId=12', 'xuanyi': 'chanId=6', 'wuxia': 'chanId=3',
            'qihuan': 'chanId=5', 'junshi': 'chanId=7', 'tiyu': 'chanId=9',
            'xianshi': 'chanId=8', 'duanpian': 'chanId=19',
        }
        cat_param = cat_map.get(category, '')
        if cat_param:
            base_url += ('&' if '?' in base_url else '?') + cat_param

        logger.info(f'[扫榜] 爬取起点(移动版): {base_url}')
        resp = session.get(base_url, timeout=15, headers=_get_headers())
        _random_delay()

        if resp.status_code != 200 or len(resp.text) < 5000:
            return None

        return self._parse_qidian_mobile_html(resp.text)

    def _parse_qidian_mobile_html(self, html: str) -> Optional[List[Dict]]:
        """解析起点移动版HTML榜单"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            books = []
            seen_titles = set()

            all_links = soup.find_all('a')
            seen = set()
            for a in all_links:
                href = a.get('href', '')
                text = a.get_text(strip=True)
                if '/book/' not in href or not text or len(text) < 10:
                    continue
                if href in seen:
                    continue
                seen.add(href)

                title = ''
                author = ''
                genre = ''

                # 去掉开头的数字排名
                text = re.sub(r'^\d+', '', text).strip()

                # 结构：书名+简介+作者·分类·X万字
                # 从右往左找·
                last_dot = text.rfind('·')
                if last_dot != -1:
                    second_last_dot = text.rfind('·', 0, last_dot)
                    if second_last_dot != -1:
                        # 作者·分类·字数
                        genre = text[second_last_dot + 1:last_dot]
                        word_count_part = text[last_dot + 1:]
                        before_author = text[:second_last_dot].rstrip('…· ')

                        # 从before_author末尾提取作者（2-6个中文字符）
                        author_match = re.search(r'([\u4e00-\u9fa5]{2,6})$', before_author)
                        if author_match:
                            author = author_match.group(1)
                            title_part = before_author[:author_match.start()].rstrip('…· ')
                        else:
                            title_part = before_author

                        # 从title_part中提取书名
                        # 书名后面通常是简介，用第一个标点/省略号分割
                        title_match = re.match(
                            r'^([\u4e00-\u9fa5a-zA-Z0-9《》]{2,12}?)(?=[。，！？…—\s"“”])',
                            title_part
                        )
                        if title_match:
                            title = title_match.group(1)
                        else:
                            # 没有明显分隔符，取前8个字
                            title = title_part[:8]

                if not title:
                    # 没有找到标准格式，取前12个字作为书名
                    title = text[:12]

                title = title.strip()
                if title and len(title) > 1 and len(title) < 30:
                    books.append({
                        'rank': len(books) + 1,
                        'title': title,
                        'author': author,
                        'genre': genre,
                        'popularity': 100 - len(books) * 2,
                    })
                if len(books) >= 20:
                    break

            return books if len(books) >= 5 else None
        except ImportError:
            return None

    # ═══════════════════════════════════════
    # 2. 起点女生网（移动版）
    # ═══════════════════════════════════════

    def _scan_qidian_girl(self, session, rank_type: str, category: str) -> Optional[List[Dict]]:
        """爬取起点女生网（移动版）"""
        url_map = {
            'yuepiao': 'https://m.qidian.com/mm/rank/yuepiao',
            'hotsales': 'https://m.qidian.com/mm/rank/hotsales',
            'recommend': 'https://m.qidian.com/mm/rank/recommend',
        }
        base_url = url_map.get(rank_type, url_map['hotsales'])
        logger.info(f'[扫榜] 爬取起点女生网(移动版): {base_url}')
        resp = session.get(base_url, timeout=15, headers=_get_headers())
        _random_delay()
        if resp.status_code != 200 or len(resp.text) < 5000:
            return None
        return self._parse_qidian_mobile_html(resp.text)

    # ═══════════════════════════════════════
    # 3. 番茄小说（解析__INITIAL_STATE__）
    # ═══════════════════════════════════════

    def _scan_fanqie(self, session, rank_type: str, category: str) -> Optional[List[Dict]]:
        """爬取番茄小说榜单（解析__INITIAL_STATE__）"""
        base_url = 'https://fanqienovel.com/rank'

        logger.info(f'[扫榜] 爬取番茄小说: {base_url}')
        resp = session.get(base_url, timeout=15, headers=_get_headers())
        _random_delay()

        if resp.status_code != 200 or len(resp.text) < 5000:
            return None

        scripts = re.findall(r'<script[^>]*>(.*?)</script>', resp.text, re.DOTALL)
        json_str = None
        for s in scripts:
            if '__INITIAL_STATE__' in s:
                json_str = extract_json_from_js(s, '__INITIAL_STATE__')
                if json_str:
                    break

        if not json_str:
            return None

        try:
            data = json.loads(json_str)
            rank_data = data.get('rank', {})
            books = []

            book_list = rank_data.get('book_list', [])
            if not book_list:
                for key in ['book_list', 'readRankList', 'newRankList']:
                    if key in rank_data and isinstance(rank_data[key], list) and len(rank_data[key]) > 0:
                        book_list = rank_data[key]
                        break

            if not book_list:
                return None

            for idx, item in enumerate(book_list[:30]):
                title = item.get('bookName') or item.get('book_name') or item.get('title') or item.get('name', '')
                author = item.get('author') or item.get('authorName') or item.get('author_name', '')
                genre = item.get('category') or item.get('categoryV2') or item.get('category_name') or ''
                if title:
                    books.append({
                        'rank': idx + 1,
                        'title': title,
                        'author': author,
                        'genre': genre,
                        'popularity': 100 - idx * 2,
                    })

            return books if books else None
        except Exception as e:
            logger.warning(f'[扫榜] 番茄小说解析失败: {e}')
            return None

    # ═══════════════════════════════════════
    # 4. 飞卢小说
    # ═══════════════════════════════════════

    def _scan_feilu(self, session, rank_type: str, category: str) -> Optional[List[Dict]]:
        """爬取飞卢小说榜单"""
        url_map = {
            'hot': 'https://b.faloo.com/Rank_1.html',
            'yuepiao': 'https://b.faloo.com/Rank_2.html',
            'dianji': 'https://b.faloo.com/Rank_3.html',
            'shoucang': 'https://b.faloo.com/Rank_4.html',
        }
        base_url = url_map.get(rank_type, url_map['hot'])

        logger.info(f'[扫榜] 爬取飞卢: {base_url}')
        try:
            resp = session.get(base_url, timeout=15, headers=_get_headers())
            _random_delay()
        except Exception:
            return None

        if resp.status_code != 200 or len(resp.text) < 5000:
            return None

        try:
            resp.encoding = 'gb2312'
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            books = []
            seen_titles = set()
            for i in range(1, 51):
                sel = f'.c_de_rk_c_d_number{i}'
                items = soup.select(sel)
                for item in items:
                    parent = item.parent
                    if not parent:
                        continue
                    # 找链接
                    link = parent.find('a')
                    if link:
                        title = link.get_text(strip=True)
                        href = link.get('href', '')
                    else:
                        title = parent.get_text(strip=True)
                        href = ''

                    if title and len(title) > 3 and len(title) < 50:
                        # 清理标题
                        title = re.sub(r'^\d+\s*', '', title).strip()
                        title = re.sub(r'^NO\.\d+\s*', '', title, flags=re.I).strip()
                        if title and title not in seen_titles:
                            books.append({
                                'rank': len(books) + 1,
                                'title': title,
                                'author': '',
                                'genre': '',
                                'popularity': 100 - len(books) * 2,
                            })
                            seen_titles.add(title)
                    if len(books) >= 20:
                        break
                if len(books) >= 20:
                    break

            if len(books) < 5:
                # 方法2：从c_de_rk_content提取
                content_blocks = soup.select('.c_de_rk_content')
                for block in content_blocks:
                    text = block.get_text(' ', strip=True)
                    # 匹配 "数字 书名" 模式
                    matches = re.findall(r'(?:^|\s)(\d+)\s+([^\s\d][^\s]{3,30})', text)
                    for rank, title in matches:
                        if title and title not in seen_titles:
                            books.append({
                                'rank': len(books) + 1,
                                'title': title,
                                'author': '',
                                'genre': '',
                                'popularity': 100 - len(books) * 2,
                            })
                            seen_titles.add(title)
                        if len(books) >= 20:
                            break
                    if len(books) >= 20:
                        break

            return books if len(books) >= 5 else None
        except ImportError:
            return None

    # ═══════════════════════════════════════
    # 5. 晋江文学城（GBK编码）
    # ═══════════════════════════════════════

    def _scan_jjwxc(self, session, rank_type: str, category: str) -> Optional[List[Dict]]:
        """爬取晋江文学城榜单（GBK编码）"""
        url_map = {
            'hot': 'https://www.jjwxc.net/topten.php?orderstr=4',
            'new': 'https://www.jjwxc.net/topten.php?orderstr=3',
            'finish': 'https://www.jjwxc.net/topten.php?orderstr=2',
            'yuedu': 'https://www.jjwxc.net/topten.php?orderstr=1',
        }
        base_url = url_map.get(rank_type, url_map['hot'])

        logger.info(f'[扫榜] 爬取晋江: {base_url}')
        try:
            resp = session.get(base_url, timeout=20, headers=_get_headers())
            _random_delay()
        except Exception:
            return None

        if resp.status_code != 200 or len(resp.text) < 5000:
            return None

        try:
            resp.encoding = 'gb18030'
            html = resp.text

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            books = []

            tables = soup.find_all('table')
            target_table = None
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) > 50:
                    first_row = rows[0]
                    cells = first_row.find_all('td')
                    if len(cells) >= 5 and '作者' in cells[0].get_text():
                        target_table = table
                        break
                    if len(cells) >= 5:
                        target_table = table
                        break

            if not target_table:
                return None

            rows = target_table.find_all('tr')
            for row in rows[1:30]:
                try:
                    cells = row.find_all('td')
                    if len(cells) < 5:
                        continue

                    rank_text = cells[0].get_text(strip=True) if len(cells) > 0 else ''
                    if not rank_text.isdigit():
                        continue

                    author = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                    title_el = cells[2].find('a') if len(cells) > 2 else None
                    title = title_el.get_text(strip=True) if title_el else ''
                    genre_full = cells[3].get_text(strip=True) if len(cells) > 3 else ''

                    genre = ''
                    if genre_full and '-' in genre_full:
                        parts = genre_full.split('-')
                        if len(parts) >= 3:
                            genre = parts[2]

                    if title and len(title) > 1:
                        books.append({
                            'rank': len(books) + 1,
                            'title': title,
                            'author': author,
                            'genre': genre,
                            'popularity': 100 - len(books) * 2,
                        })
                except Exception:
                    continue

            return books if len(books) >= 5 else None
        except ImportError:
            return None

    # ═══════════════════════════════════════
    # 6. 七猫小说
    # ═══════════════════════════════════════

    def _scan_qimao(self, session, rank_type: str, category: str) -> Optional[List[Dict]]:
        """爬取七猫小说榜单（解析__NUXT__）"""
        base_url = 'https://www.qimao.com/rank/'

        logger.info(f'[扫榜] 爬取七猫: {base_url}')
        try:
            resp = session.get(base_url, timeout=15, headers=_get_headers())
            _random_delay()
        except Exception:
            return None

        if resp.status_code != 200:
            return None

        # 尝试提取__NUXT__数据
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', resp.text, re.DOTALL)
        json_str = None
        for s in scripts:
            if '__NUXT__' in s:
                json_str = extract_json_from_js(s, '__NUXT__')
                if json_str:
                    break

        if json_str:
            try:
                data = json.loads(json_str)
                books = []
                # 七猫NUXT数据结构可能比较深，遍历查找书籍列表
                def find_book_list(obj, depth=0):
                    if depth > 10:
                        return None
                    if isinstance(obj, list) and len(obj) > 0:
                        if isinstance(obj[0], dict) and any(k in obj[0] for k in ['bookName', 'title', 'name', 'book_name']):
                            return obj
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            result = find_book_list(v, depth + 1)
                            if result:
                                return result
                    return None

                book_list = find_book_list(data)
                if book_list:
                    for idx, item in enumerate(book_list[:30]):
                        title = (item.get('book_name') or item.get('bookName') or
                                item.get('title') or item.get('name', ''))
                        author = item.get('author') or item.get('authorName', '')
                        genre = item.get('category') or item.get('categoryName', '')
                        if title:
                            books.append({
                                'rank': idx + 1,
                                'title': title,
                                'author': author,
                                'genre': genre,
                                'popularity': 100 - idx * 2,
                            })
                    return books if books else None
            except Exception as e:
                logger.warning(f'[扫榜] 七猫NUXT解析失败: {e}')

        # 降级到HTML解析
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            books = []
            items = (soup.select('.rank-list .rank-item') or
                    soup.select('.book-list .book-item') or
                    soup.select('[class*="rank"] [class*="item"]'))
            for idx, item in enumerate(items[:30]):
                try:
                    title_el = item.select_one('.book-name a') or item.select_one('.title a') or item.select_one('a')
                    title = title_el.get_text(strip=True) if title_el else ''
                    author_el = item.select_one('.author')
                    author = author_el.get_text(strip=True) if author_el else ''
                    genre_el = item.select_one('.category') or item.select_one('.cat')
                    genre = genre_el.get_text(strip=True) if genre_el else ''
                    if title and len(title) > 1:
                        books.append({
                            'rank': idx + 1,
                            'title': title,
                            'author': author,
                            'genre': genre,
                            'popularity': 100 - idx * 2,
                        })
                except Exception:
                    continue
            return books if books else None
        except ImportError:
            return None

    # ═══════════════════════════════════════
    # 7. 刺猬猫
    # ═══════════════════════════════════════

    def _scan_ciweimao(self, session, rank_type: str, category: str) -> Optional[List[Dict]]:
        """爬取刺猬猫榜单"""
        url_map = {
            'hot': 'https://www.ciweimao.com/rank/hot',
            'new': 'https://www.ciweimao.com/rank/new',
            'yuepiao': 'https://www.ciweimao.com/rank/yuepiao',
            'shoucang': 'https://www.ciweimao.com/rank/collect',
        }
        base_url = url_map.get(rank_type, url_map['hot'])

        logger.info(f'[扫榜] 爬取刺猬猫: {base_url}')
        try:
            resp = session.get(base_url, timeout=15, headers=_get_headers())
            _random_delay()
        except Exception:
            return None

        if resp.status_code != 200:
            return None

        # 尝试从内嵌JSON提取
        json_str = extract_json_from_js(resp.text, '__NUXT__')
        if not json_str:
            json_str = extract_json_from_js(resp.text, '__INITIAL_STATE__')

        if json_str:
            try:
                data = json.loads(json_str)
                books = []
                def find_book_list(obj, depth=0):
                    if depth > 10:
                        return None
                    if isinstance(obj, list) and len(obj) > 0:
                        if isinstance(obj[0], dict) and any(k in obj[0] for k in ['bookName', 'title', 'name', 'book_name']):
                            return obj
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            result = find_book_list(v, depth + 1)
                            if result:
                                return result
                    return None

                book_list = find_book_list(data)
                if book_list:
                    for idx, item in enumerate(book_list[:30]):
                        title = (item.get('book_name') or item.get('bookName') or
                                item.get('title') or item.get('name', ''))
                        author = item.get('author') or item.get('authorName', '')
                        genre = item.get('category') or item.get('categoryName', '')
                        if title:
                            books.append({
                                'rank': idx + 1,
                                'title': title,
                                'author': author,
                                'genre': genre,
                                'popularity': 100 - idx * 2,
                            })
                    return books if books else None
            except Exception:
                pass

        # HTML解析降级
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            books = []
            items = (soup.select('.rank-list .rank-item') or
                    soup.select('.book-list .book-item') or
                    soup.select('[class*="rank"] [class*="item"]'))
            for idx, item in enumerate(items[:30]):
                try:
                    title_el = item.select_one('.book-name a') or item.select_one('.title a') or item.select_one('a')
                    title = title_el.get_text(strip=True) if title_el else ''
                    author_el = item.select_one('.author')
                    author = author_el.get_text(strip=True) if author_el else ''
                    if title and len(title) > 1:
                        books.append({
                            'rank': idx + 1,
                            'title': title,
                            'author': author,
                            'genre': '',
                            'popularity': 100 - idx * 2,
                        })
                except Exception:
                    continue
            return books if books else None
        except ImportError:
            return None

    # ═══════════════════════════════════════
    # 8. 纵横中文网
    # ═══════════════════════════════════════

    def _scan_zongheng(self, session, rank_type: str, category: str) -> Optional[List[Dict]]:
        """爬取纵横中文网榜单"""
        url_map = {
            'yuepiao': 'https://www.zongheng.com/rank/yuepiao.html',
            'hot': 'https://www.zongheng.com/rank/hotsales.html',
            'dianji': 'https://www.zongheng.com/rank/dianji.html',
            'shoucang': 'https://www.zongheng.com/rank/shoucang.html',
            'newbook': 'https://www.zongheng.com/rank/newbook.html',
        }
        base_url = url_map.get(rank_type, url_map['hot'])

        logger.info(f'[扫榜] 爬取纵横: {base_url}')
        try:
            resp = session.get(base_url, timeout=15, headers=_get_headers())
            _random_delay()
        except Exception:
            return None

        if resp.status_code != 200:
            return None

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            books = []

            items = (soup.select('.rank-list .rank-item') or
                    soup.select('.rank-list li') or
                    soup.select('.book-list .book-item') or
                    soup.select('[class*="rank"] [class*="item"]'))

            for idx, item in enumerate(items[:30]):
                try:
                    title_el = (item.select_one('.book-name a') or
                               item.select_one('.title a') or
                               item.select_one('.rank_book a') or
                               item.select_one('a[href*="/book/"]'))
                    title = title_el.get_text(strip=True) if title_el else ''

                    author_el = (item.select_one('.author') or
                                item.select_one('.writer') or
                                item.select_one('.author_name'))
                    author = author_el.get_text(strip=True) if author_el else ''

                    genre_el = (item.select_one('.category') or
                               item.select_one('.cat') or
                               item.select_one('.type'))
                    genre = genre_el.get_text(strip=True) if genre_el else ''

                    if title and len(title) > 1:
                        books.append({
                            'rank': idx + 1,
                            'title': title,
                            'author': author,
                            'genre': genre,
                            'popularity': 100 - idx * 2,
                        })
                except Exception:
                    continue

            return books if books else None
        except ImportError:
            return None
