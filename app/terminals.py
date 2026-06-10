import yaml
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

TERMINALS_FILE = Path(__file__).parent.parent / "terminals.yaml"


@dataclass
class Terminal:
    ip: str
    alias: str
    group: str = "default"
    port: int = 8081
    online: bool = False
    config_version: Optional[str] = None


def load_terminals() -> list[Terminal]:
    """从 YAML 加载终端列表"""
    if not TERMINALS_FILE.exists():
        return []
    with open(TERMINALS_FILE) as f:
        data = yaml.safe_load(f)
    terminals = []
    for t in data.get("terminals", []):
        terminals.append(Terminal(
            ip=t["ip"],
            alias=t.get("alias", t["ip"]),
            group=t.get("group", "default"),
            port=t.get("port", 8081),
        ))
    return terminals


def get_terminal_groups(terminals: list[Terminal]) -> list[str]:
    """获取所有分组名"""
    groups = set()
    for t in terminals:
        groups.add(t.group)
    return sorted(groups)
