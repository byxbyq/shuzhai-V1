# -*- coding: utf-8 -*-
import os
import difflib
from fastapi import APIRouter, Depends

from backend.services.project_service import state
from backend.api_models import paginated, PaginationParams, err, ErrorCode
import logging

logger = logging.getLogger(__name__)

from ._utils import SnapshotRestore, SnapshotDiff

router = APIRouter()

@router.get("/snapshots")
def chapter_snapshots(index: int = 0, pagination: PaginationParams = Depends()):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    snapshots = state.project.get_snapshots(index)
    total = len(snapshots)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    return paginated(snapshots[start:end], pagination.page, pagination.page_size, total)

@router.post("/snapshot/restore")
def restore_snapshot(data: SnapshotRestore):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = state.project.restore_snapshot(data.index, data.snapshot_file)
    return {"ok": ok}

@router.post("/snapshot/diff")
def diff_snapshot(data: SnapshotDiff):
    """比较两个快照文件的差异，返回结构化diff及两份完整内容"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    snap_dir = os.path.join(state.project.project_dir, "snapshots")
    path_a = os.path.join(snap_dir, data.snapshot_a)
    path_b = os.path.join(snap_dir, data.snapshot_b)
    # 安全检查：防止路径穿越
    if not os.path.realpath(path_a).startswith(os.path.realpath(snap_dir)):
        return err(ErrorCode.INTERNAL_ERROR, "非法的快照文件名(snapshot_a)")
    if not os.path.realpath(path_b).startswith(os.path.realpath(snap_dir)):
        return err(ErrorCode.INTERNAL_ERROR, "非法的快照文件名(snapshot_b)")
    if not os.path.exists(path_a):
        return err(ErrorCode.NOT_FOUND, f"快照文件不存在: {data.snapshot_a}")
    if not os.path.exists(path_b):
        return err(ErrorCode.NOT_FOUND, f"快照文件不存在: {data.snapshot_b}")
    try:
        with open(path_a, "r", encoding="utf-8") as f:
            content_a = f.read()
        with open(path_b, "r", encoding="utf-8") as f:
            content_b = f.read()
    except Exception as e:
        logger.warning(f"读取快照失败: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"读取快照失败: {e}")

    lines_a = content_a.splitlines()
    lines_b = content_b.splitlines()

    # 使用 difflib.ndiff 逐行比较，标记每行类型
    sm = difflib.SequenceMatcher(a=lines_a, b=lines_b, autojunk=False)
    diff = []
    added_lines = 0
    removed_lines = 0
    changed_blocks = 0
    in_change_block = False

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for line in lines_a[i1:i2]:
                diff.append({"type": "unchanged", "text": line})
            in_change_block = False
        elif tag == "delete":
            for line in lines_a[i1:i2]:
                diff.append({"type": "removed", "text": line})
                removed_lines += 1
            if not in_change_block:
                changed_blocks += 1
                in_change_block = True
        elif tag == "insert":
            for line in lines_b[j1:j2]:
                diff.append({"type": "added", "text": line})
                added_lines += 1
            if not in_change_block:
                changed_blocks += 1
                in_change_block = True
        elif tag == "replace":
            for line in lines_a[i1:i2]:
                diff.append({"type": "removed", "text": line})
                removed_lines += 1
            for line in lines_b[j1:j2]:
                diff.append({"type": "added", "text": line})
                added_lines += 1
            if not in_change_block:
                changed_blocks += 1
                in_change_block = True

    return {
        "ok": True,
        "diff": diff,
        "stats": {
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "changed_blocks": changed_blocks
        },
        "content_a": content_a,
        "content_b": content_b
    }
