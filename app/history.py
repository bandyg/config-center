"""Kiosk Config Center — 配置历史记录与回滚管理

以 JSON 文件存储每次配置修改的历史记录。
存储路径: {base_dir}/history/{ip}/{key}.jsonl
每个文件按行存储，每行一个 JSON 对象代表一次修改记录。
"""

import json
import os
import time
from pathlib import Path

# 历史记录存储目录
HISTORY_DIR = Path(os.environ.get("KIOSK_CONFIG_BASE_DIR", str(Path(__file__).parent))) / "history"


def _ensure_history_dir(ip: str, key: str):
    """确保历史记录目录存在"""
    d = HISTORY_DIR / ip
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.jsonl"


def record_config_change(ip: str, alias: str, key: str, old_value, new_value):
    """记录配置修改历史

    Args:
        ip: 终端 IP
        alias: 终端别名
        key: 配置项名称
        old_value: 修改前的值（dict）
        new_value: 修改后的值（dict）
    """
    filepath = _ensure_history_dir(ip, key)
    record = {
        "timestamp": time.time(),
        "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "ip": ip,
        "alias": alias,
        "key": key,
        "old_value": old_value,
        "new_value": new_value,
    }
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_config_history(ip: str, key: str, limit: int = 50):
    """获取指定终端指定配置项的修改历史

    Args:
        ip: 终端 IP
        key: 配置项名称
        limit: 最多返回条数

    Returns:
        历史记录列表（按时间倒序）
    """
    filepath = HISTORY_DIR / ip / f"{key}.jsonl"
    if not filepath.exists():
        return []

    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # 按时间倒序排列
    records.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
    return records[:limit]


def get_latest_config(ip: str, key: str):
    """获取最近一次保存的配置值（用于回滚时作 Diff）"""
    records = get_config_history(ip, key, limit=1)
    if records:
        return records[0].get("new_value")
    return None


def rollback_config(ip: str, key: str, target_timestamp: float):
    """回滚到指定时间点的配置版本

    回滚逻辑：找到目标版本对应的 new_value，将其作为本次修改写入记录

    Args:
        ip: 终端 IP
        key: 配置项名称
        target_timestamp: 目标版本的时间戳

    Returns:
        (成功?, 回滚后的值, 错误信息)
    """
    records = get_config_history(ip, key, limit=200)
    target = None
    for r in records:
        if abs(r.get("timestamp", 0) - target_timestamp) < 0.001:
            target = r
            break

    if not target:
        return False, None, "未找到指定版本的历史记录"

    rollback_value = target.get("new_value")
    current_value = get_latest_config(ip, key)

    if current_value == rollback_value:
        return False, None, "当前配置已经是该版本，无需回滚"

    # 记录回滚操作
    record_config_change(
        ip=ip,
        alias=target.get("alias", ""),
        key=key,
        old_value=current_value,
        new_value=rollback_value,
    )

    return True, rollback_value, None
