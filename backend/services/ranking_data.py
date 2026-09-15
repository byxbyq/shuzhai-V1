# -*- coding: utf-8 -*-
"""排行服务模块级常量、工具函数和降级数据（从 ranking_service.py 拆分）"""
import os, re, json, time, random, datetime, logging
from typing import Optional

logger = logging.getLogger(__name__)

from backend.runtime_paths import get_app_root
PROJECT_ROOT = get_app_root()
RANKING_DIR = os.path.join(PROJECT_ROOT, 'data', 'ranking')
os.makedirs(RANKING_DIR, exist_ok=True)

# ═══════════════════════════════════════════
# 平台配置
# ═══════════════════════════════════════════

PLATFORM_CONFIG = {
    'qidian': {
        'name': '起点中文网',
        'url': 'https://www.qidian.com',
        'rank_types': {
            'yuepiao': '月票榜',
            'hotsales': '热销榜',
            'recommend': '推荐榜',
            'hits': '点击榜',
            'collect': '收藏榜',
            'newbook': '新书榜',
        },
        'categories': {
            'all': '全部', 'xuanhuan': '玄幻', 'dushi': '都市', 'xianxia': '仙侠',
            'kehuan': '科幻', 'lishi': '历史', 'youxi': '游戏',
            'qingxiaoshuo': '轻小说', 'xuanyi': '悬疑', 'wuxia': '武侠',
            'qihuan': '奇幻', 'junshi': '军事', 'tiyu': '体育',
            'xianshi': '现实', 'duanpian': '短篇',
        },
    },
    'qidian_girl': {
        'name': '起点女生网',
        'url': 'https://www.qidian.com/mm/',
        'rank_types': {
            'yuepiao': '月票榜',
            'hotsales': '热销榜',
            'recommend': '推荐榜',
        },
        'categories': {
            'all': '全部', 'gudai': '古代言情', 'xianyan': '现代言情',
            'xuanhuan': '玄幻言情', 'xianxia': '仙侠奇缘',
            'kehuan': '科幻空间', 'youxi': '游戏竞技',
            'lishi': '历史军事', 'xuanyi': '悬疑推理',
        },
    },
    'fanqie': {
        'name': '番茄小说',
        'url': 'https://fanqienovel.com',
        'rank_types': {
            'hot': '热榜',
            'new': '新书榜',
            'finish': '完结榜',
        },
        'categories': {
            'all': '全部', 'xuanhuan': '玄幻', 'dushi': '都市', 'xianxia': '仙侠',
            'kehuan': '科幻', 'lishi': '历史', 'youxi': '游戏',
            'qingxiaoshuo': '轻小说', 'xuanyi': '悬疑', 'wuxia': '武侠',
            'xianyan': '现言', 'gudai': '古言',
        },
    },
    'feilu': {
        'name': '飞卢小说',
        'url': 'https://b.faloo.com',
        'rank_types': {
            'hot': '热搜榜',
            'yuepiao': '月票榜',
            'dianji': '点击榜',
            'shoucang': '收藏榜',
        },
        'categories': {
            'all': '全部', 'xuanhuan': '玄幻', 'dushi': '都市', 'xianxia': '仙侠',
            'kehuan': '科幻', 'youxi': '游戏', 'ertong': '同人',
            'lishi': '历史', 'junshi': '军事', 'xuanyi': '悬疑',
        },
    },
    'jjwxc': {
        'name': '晋江文学城',
        'url': 'https://www.jjwxc.net',
        'rank_types': {
            'hot': '积分榜',
            'new': '新秀榜',
            'finish': '完结榜',
            'yuedu': '阅读榜',
        },
        'categories': {
            'all': '全部', 'gudai': '古色古香', 'xianyan': '现代言情',
            'yuancheng': '原创', 'chunai': '纯爱', 'qingxiaoshuo': '轻小说',
            'xuanyi': '悬疑', 'kehuan': '科幻', 'lishi': '历史',
        },
    },
    'qimao': {
        'name': '七猫小说',
        'url': 'https://www.qimao.com',
        'rank_types': {
            'hot': '热销榜',
            'new': '新书榜',
            'finish': '完结榜',
            'recommend': '推荐榜',
        },
        'categories': {
            'all': '全部', 'xuanhuan': '玄幻', 'dushi': '都市', 'xianxia': '仙侠',
            'kehuan': '科幻', 'lishi': '历史', 'youxi': '游戏',
            'xuanyi': '悬疑', 'wuxia': '武侠', 'qihuan': '奇幻',
            'xianyan': '现言', 'gudai': '古言',
        },
    },
    'ciweimao': {
        'name': '刺猬猫',
        'url': 'https://www.ciweimao.com',
        'rank_types': {
            'hot': '热销榜',
            'new': '新书榜',
            'yuepiao': '月票榜',
            'shoucang': '收藏榜',
        },
        'categories': {
            'all': '全部', 'qingxiaoshuo': '轻小说', 'xuanhuan': '玄幻',
            'youxi': '游戏', 'kehuan': '科幻', 'dushi': '都市',
            'xianxia': '仙侠', 'xuanyi': '悬疑',
        },
    },
    'zongheng': {
        'name': '纵横中文网',
        'url': 'https://www.zongheng.com',
        'rank_types': {
            'yuepiao': '月票榜',
            'hot': '热销榜',
            'dianji': '点击榜',
            'shoucang': '收藏榜',
            'newbook': '新书榜',
        },
        'categories': {
            'all': '全部', 'xuanhuan': '玄幻', 'dushi': '都市', 'xianxia': '仙侠',
            'kehuan': '科幻', 'lishi': '历史', 'youxi': '游戏',
            'xuanyi': '悬疑', 'wuxia': '武侠', 'qihuan': '奇幻',
            'junshi': '军事', 'xianyan': '现言', 'gudai': '古言',
        },
    },
}

# ═══════════════════════════════════════════
# User-Agent 轮换池
# ═══════════════════════════════════════════

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
]

REQUEST_INTERVAL_MIN = 1.5
REQUEST_INTERVAL_MAX = 3.0
CACHE_TTL_HOURS = 6


def _get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
    }


def _random_delay():
    delay = random.uniform(REQUEST_INTERVAL_MIN, REQUEST_INTERVAL_MAX)
    time.sleep(delay)


def _cache_path(key: str) -> str:
    return os.path.join(RANKING_DIR, f'{key}.json')


def _save_cache(key: str, data: dict):
    data['_cached_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(_cache_path(key), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f'保存缓存失败 {key}: {e}')


def _load_cache(key: str) -> Optional[dict]:
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cached_at = data.get('_cached_at', '')
        if cached_at:
            try:
                cached_dt = datetime.datetime.strptime(cached_at, '%Y-%m-%d %H:%M:%S')
                if (datetime.datetime.now() - cached_dt).total_seconds() < CACHE_TTL_HOURS * 3600:
                    return data
            except ValueError:
                pass
        return None
    except Exception as e:
        logger.warning(f'加载缓存失败 {key}: {e}')
        return None


def extract_json_from_js(text: str, var_name: str) -> Optional[str]:
    """从JS代码中提取指定变量的JSON值（处理括号嵌套和字符串转义）

    支持两种形式：
    1. VAR = {...}  直接赋值对象
    2. VAR = (function(){return {...}})()  IIFE函数调用（如Nuxt）
    """
    pattern = re.escape(var_name) + r'\s*=\s*'
    m = re.search(pattern, text)
    if not m:
        return None
    start = m.end()
    if start >= len(text):
        return None

    def _find_matching_brace(s, start_idx):
        """从start_idx位置开始，找到匹配的{}或[]"""
        if start_idx >= len(s):
            return None
        if s[start_idx] not in '{[':
            return None
        open_char = s[start_idx]
        close_char = '}' if open_char == '{' else ']'
        count = 0
        in_string = False
        string_char = None
        escape = False
        for i in range(start_idx, len(s)):
            c = s[i]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if in_string:
                if c == string_char:
                    in_string = False
                continue
            if c in '"\'':
                in_string = True
                string_char = c
                continue
            if c == open_char:
                count += 1
            elif c == close_char:
                count -= 1
                if count == 0:
                    return s[start_idx:i+1]
        return None

    # 情况1：直接赋值对象 VAR = {...}
    if text[start] in '{[':
        return _find_matching_brace(text, start)

    # 情况2：IIFE函数调用 VAR = (function(...){return {...}})()
    if text[start] == '(':
        # 寻找 return { 或 return [
        return_pattern = r'return\s+([{\[])'
        rm = re.search(return_pattern, text[start:start+5000])
        if rm:
            return_start = start + rm.start(1)
            return _find_matching_brace(text, return_start)

    return None


# ═══════════════════════════════════════════
# 内置降级数据
# ═══════════════════════════════════════════

FALLBACK_GENRES = {
    '玄幻': {'popularity': 95, 'trend': 'stable', 'competition': 'intense', 'avg_readers': 85000},
    '都市': {'popularity': 92, 'trend': 'stable', 'competition': 'intense', 'avg_readers': 82000},
    '仙侠': {'popularity': 88, 'trend': 'rising', 'competition': 'intense', 'avg_readers': 78000},
    '科幻': {'popularity': 75, 'trend': 'rising', 'competition': 'moderate', 'avg_readers': 55000},
    '历史': {'popularity': 72, 'trend': 'stable', 'competition': 'moderate', 'avg_readers': 48000},
    '游戏': {'popularity': 80, 'trend': 'rising', 'competition': 'moderate', 'avg_readers': 62000},
    '轻小说': {'popularity': 85, 'trend': 'rising', 'competition': 'moderate', 'avg_readers': 70000},
    '悬疑': {'popularity': 70, 'trend': 'stable', 'competition': 'low', 'avg_readers': 42000},
    '武侠': {'popularity': 55, 'trend': 'declining', 'competition': 'low', 'avg_readers': 25000},
    '奇幻': {'popularity': 78, 'trend': 'rising', 'competition': 'moderate', 'avg_readers': 58000},
    '军事': {'popularity': 45, 'trend': 'declining', 'competition': 'low', 'avg_readers': 18000},
    '体育': {'popularity': 40, 'trend': 'stable', 'competition': 'low', 'avg_readers': 15000},
    '现实': {'popularity': 60, 'trend': 'rising', 'competition': 'low', 'avg_readers': 35000},
    '短篇': {'popularity': 35, 'trend': 'stable', 'competition': 'low', 'avg_readers': 10000},
    '古言': {'popularity': 85, 'trend': 'stable', 'competition': 'intense', 'avg_readers': 75000},
    '现言': {'popularity': 82, 'trend': 'stable', 'competition': 'intense', 'avg_readers': 72000},
}

FALLBACK_RANKING = [
    {'rank': 1, 'title': '大奉打更人', 'author': '卖报小郎君', 'genre': '仙侠', 'popularity': 98},
    {'rank': 2, 'title': '诡秘之主', 'author': '爱潜水的乌贼', 'genre': '奇幻', 'popularity': 97},
    {'rank': 3, 'title': '夜的命名术', 'author': '会说话的肘子', 'genre': '科幻', 'popularity': 96},
    {'rank': 4, 'title': '深空彼岸', 'author': '辰东', 'genre': '玄幻', 'popularity': 95},
    {'rank': 5, 'title': '灵境行者', 'author': '卖报小郎君', 'genre': '都市', 'popularity': 94},
    {'rank': 6, 'title': '择日飞升', 'author': '宅猪', 'genre': '仙侠', 'popularity': 93},
    {'rank': 7, 'title': '光阴之外', 'author': '耳根', 'genre': '仙侠', 'popularity': 92},
    {'rank': 8, 'title': '赤心巡天', 'author': '情何以甚', 'genre': '仙侠', 'popularity': 91},
    {'rank': 9, 'title': '明克街13号', 'author': '纯洁滴小龙', 'genre': '奇幻', 'popularity': 90},
    {'rank': 10, 'title': '我的治愈系游戏', 'author': '我会修空调', 'genre': '悬疑', 'popularity': 89},
    {'rank': 11, 'title': '星门', 'author': '老鹰吃小鸡', 'genre': '科幻', 'popularity': 88},
    {'rank': 12, 'title': '长夜余火', 'author': '爱潜水的乌贼', 'genre': '科幻', 'popularity': 87},
    {'rank': 13, 'title': '轮回乐园', 'author': '那一只蚊子', 'genre': '游戏', 'popularity': 86},
    {'rank': 14, 'title': '超神机械师', 'author': '齐佩甲', 'genre': '游戏', 'popularity': 85},
    {'rank': 15, 'title': '绍宋', 'author': '榴弹怕水', 'genre': '历史', 'popularity': 84},
    {'rank': 16, 'title': '秦吏', 'author': '七月新番', 'genre': '历史', 'popularity': 83},
    {'rank': 17, 'title': '全球高武', 'author': '老鹰吃小鸡', 'genre': '都市', 'popularity': 82},
    {'rank': 18, 'title': '大王饶命', 'author': '会说话的肘子', 'genre': '都市', 'popularity': 81},
    {'rank': 19, 'title': '我有一座恐怖屋', 'author': '我会修空调', 'genre': '悬疑', 'popularity': 80},
    {'rank': 20, 'title': '凡人修仙传', 'author': '忘语', 'genre': '仙侠', 'popularity': 79},
]

SUGGESTION_TEMPLATES = {
    '玄幻': [
        '玄幻题材竞争激烈，建议在开篇3章内建立独特的世界观差异点',
        '当前热门趋势：系统流、签到流、数据化面板仍是流量密码',
        '避免"废材逆袭"老套路，尝试"满级大佬进新手村"等反差设定',
        '章节节奏：每2000-3000字设置一个小爽点，8000字一个大高潮',
    ],
    '都市': [
        '都市题材关注现实代入感，建议加入当下热点元素增加共鸣',
        '神豪文、重生文仍具市场，但需新意（如"带着系统回90年代"）',
        '男女频融合趋势明显，适当加入感情线可扩大读者群',
        '注意：敏感题材（官场、黑道）有封禁风险，建议避开',
    ],
    '仙侠': [
        '仙侠题材读者粘性高，但要求世界观完整、逻辑自洽',
        '当前趋势：古典仙侠回潮、"苟道"流、稳健流热度上升',
        '灵气复苏+修仙是近期新热点，可以尝试',
        '境界体系设计要清晰，避免战力崩坏',
    ],
    '科幻': [
        '科幻题材读者质量高，但准入门槛也高',
        '热门方向：末日废土、星际文明、赛博朋克、进化变异',
        '建议：即使软科幻也要保证基本科学逻辑，避免硬伤',
        '融合玄幻/仙侠元素的"科玄"流派正在兴起',
    ],
    '轻小说': [
        '轻小说读者年轻化，偏好快节奏、轻松搞笑风格',
        '热门标签：穿越、异世界、转生、恶役千金、退队流',
        '章末必须有钩子，保持日更节奏',
        '标题党策略有效："我在异世界XXX"类标题点击率高',
    ],
    '悬疑': [
        '悬疑题材读者期望高，对逻辑和伏笔要求严格',
        '热门方向：无限流、规则怪谈、灵异复苏、恐怖解谜',
        '建议：每章结尾留悬念，但不要每章都"一惊一乍"',
        '伏笔回收是读者最看重的点，建议提前规划',
    ],
    '古言': [
        '古言题材读者粘性高，喜欢细腻的情感描写和人物成长',
        '热门方向：重生复仇、宅斗宫斗、经商种田、穿越',
        '建议：注意历史细节的真实性，避免重大常识错误',
        '男女主感情发展要自然，避免"一见钟情"的俗套',
    ],
    '现言': [
        '现言题材贴近生活，容易引起读者共鸣',
        '热门方向：总裁豪门、都市婚恋、职场励志、破镜重圆',
        '建议：加入现实议题（职场、家庭、成长）提升深度',
        '避免"傻白甜"女主，独立自强的人设更受欢迎',
    ],
    'default': [
        '开篇3000字内必须出现核心卖点（金手指/冲突/悬念）',
        '章节结尾留钩子，保持读者追读欲望',
        '前10章是"黄金留存期"，节奏要快，信息密度要适中',
        '关注榜单热门书的前3章写法，分析其钩子策略',
        '保持稳定更新频率，日更3000-6000字是最佳节奏',
        '读者互动：及时回复评论，培养核心粉丝群',
        '封面和简介是"第一印象"，投入时间打磨',
        '新书期关注"推荐票"和"收藏"数据，及时调整策略',
    ],
}

