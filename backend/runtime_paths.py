# -*- coding: utf-8 -*-
"""运行时路径处理 - 兼容开发模式和PyInstaller打包模式"""
import os, sys

# 当前用户（由auth中间件设置）
_current_user = 'default'

def set_current_user(username):
    global _current_user
    _current_user = username or 'default'

def get_current_user():
    return _current_user

def is_frozen():
    """是否运行在PyInstaller打包环境中"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def get_app_root():
    """获取应用根目录"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_frontend_dir():
    """获取前端文件目录"""
    # APK 环境由 Java 层通过环境变量传入
    env_dir = os.environ.get('SHUZHAI_FRONTEND_DIR')
    if env_dir:
        return env_dir
    if is_frozen():
        # 打包模式：前端文件在exe同目录的frontend文件夹
        return os.path.join(get_app_root(), 'frontend')
    else:
        return os.path.join(get_app_root(), 'frontend')

def get_data_dir():
    """获取数据目录（用户数据，需要可写）"""
    # APK 环境由 Java 层通过环境变量传入，优先使用
    env_dir = os.environ.get('SHUZHAI_DATA_DIR')
    if env_dir:
        return env_dir
    return os.path.join(get_app_root(), 'data')

def get_projects_dir():
    """获取项目目录（根据当前用户动态返回）"""
    if _current_user and _current_user != 'default':
        return get_user_projects_dir(_current_user)
    base = os.path.join(get_data_dir(), 'novel_projects')
    os.makedirs(base, exist_ok=True)
    return base

def get_user_projects_dir(username):
    """获取用户项目目录"""
    base = os.path.join(get_data_dir(), 'users', username, 'projects')
    os.makedirs(base, exist_ok=True)
    return base

def get_auth_dir():
    """获取认证数据目录"""
    return os.path.join(get_data_dir(), 'auth')

def get_shared_memory_dir():
    """获取共享记忆目录"""
    return os.path.join(get_projects_dir(), '_shared')

def get_last_project_file():
    """获取最后项目记录文件"""
    return os.path.join(get_data_dir(), 'last_project.txt')
