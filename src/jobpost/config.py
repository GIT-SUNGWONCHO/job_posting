"""config/ 폴더의 설정 파일을 읽는다.

기준 목록(직무 유형·스킬·업종·고정 선택지)은 config/taxonomy/가 원본이다. job_types·skills는 그 보기를,
profile·match_guide는 파일 내용에 기준 목록을 합친 것을 돌려준다(taxonomy.py).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _file(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / f"{name}.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@cache
def load(name: str) -> dict[str, Any]:
    from . import taxonomy

    if name == "job_types":
        return taxonomy.job_types_view()
    if name == "skills":
        return taxonomy.skills_view()
    if name == "profile":
        return {**_file(name), **taxonomy.profile_extras()}
    if name == "match_guide":
        return {**_file(name), **taxonomy.match_guide_extras()}
    return _file(name)
