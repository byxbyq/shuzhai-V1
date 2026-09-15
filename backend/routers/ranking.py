# -*- coding: utf-8 -*-
"""扫榜/市场调研路由 - /api/ranking/*（多平台版）"""
from fastapi import APIRouter, Query
from typing import Optional

from backend.services.ranking_service import RankingService

router = APIRouter(prefix="/api/ranking")

_ranking_service = RankingService()


@router.get("/platforms")
def get_platforms():
    """获取所有支持的平台配置"""
    return _ranking_service.get_platform_config()


@router.get("/scan")
def scan_ranking(
    platform: str = Query('qidian', description='平台: qidian/qidian_girl/fanqie/feilu/jjwxc/qimao/ciweimao/zongheng'),
    rank_type: str = Query('hot', description='榜单类型'),
    category: str = Query('all', description='分类')
):
    """扫榜，爬取指定平台的榜单数据"""
    result = _ranking_service.scan_ranking(platform=platform, rank_type=rank_type, category=category)
    return result


@router.get("/compare")
def compare_platforms(
    rank_type: str = Query('hot', description='榜单类型'),
    platforms: Optional[str] = Query(None, description='平台列表，逗号分隔')
):
    """多平台榜单对比"""
    pf_list = platforms.split(',') if platforms else None
    result = _ranking_service.compare_platforms(rank_type=rank_type, platforms=pf_list)
    return result


@router.get("/trends")
def get_trends(
    days: int = Query(30, ge=1, le=90, description='统计天数'),
    platform: str = Query('all', description='平台')
):
    """获取趋势变化数据"""
    result = _ranking_service.get_trends(days=days, platform=platform)
    return result


@router.get("/suggestions")
def get_suggestions(genre: str = Query('', description='题材名称')):
    """获取创作建议（基于市场数据）"""
    book_info = {'genre': genre} if genre else {}
    result = _ranking_service.get_suggestions(book_info)
    return result


@router.get("/genre-analysis")
def analyze_genre(
    genre: str = Query(..., description='题材名称，如"玄幻"、"都市"'),
    platform: str = Query('all', description='平台')
):
    """分析指定题材的市场表现"""
    result = _ranking_service.analyze_genre(genre=genre, platform=platform)
    return result
