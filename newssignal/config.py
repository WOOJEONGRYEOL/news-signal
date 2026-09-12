"""설정 — config.toml(선택)을 읽고, 없으면 기본값. 경로는 프로젝트 루트 기준."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    root: Path = ROOT
    home_press: str = "채널A"          # 대시보드에서 따로 보여줄 '우리 회사' 랭킹
    interval_minutes: int = 30
    news_search_limit: int = 25        # 한 번 수집할 때 구글 뉴스 검색으로 기사 보강할 최대 키워드 수
    top_n: int = 10
    keep_n: int = 20                   # 이력 파일에 남길 순위 수(시계열용)
    weights: dict = field(default_factory=lambda: {"search": 0.35, "publish": 0.30, "consume": 0.15, "spike": 0.20})
    baseline_days: int = 7             # 급상승 판단 기준: 지난 N일 평균 기사 수
    region_codes: list[str] = field(default_factory=list)  # 빈 목록 = 17개 시·도 전부

    @property
    def db_path(self) -> Path:
        return self.root / "data" / "newssignal.sqlite3"

    @property
    def site_dir(self) -> Path:
        return self.root / "site"

    @property
    def stopwords_file(self) -> Path:
        return self.root / "data" / "stopwords.txt"


def load(root: Path | None = None) -> Config:
    cfg = Config(root=root or ROOT)
    f = cfg.root / "config.toml"
    if f.exists():
        data = tomllib.loads(f.read_text(encoding="utf-8"))
        for k in ("home_press", "interval_minutes", "news_search_limit", "top_n", "keep_n", "region_codes", "baseline_days"):
            if k in data:
                setattr(cfg, k, data[k])
        if "weights" in data:
            w = {**cfg.weights, **data["weights"]}
            total = sum(w.values()) or 1.0
            cfg.weights = {k: v / total for k, v in w.items()}
    return cfg
