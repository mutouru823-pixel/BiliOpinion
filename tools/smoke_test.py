# -*- coding: utf-8 -*-
"""
冒烟测试：把 raw/ 下数据抽样成小集合，用 config_validate.yaml 跑通整条管线，
用于在上全量（~12 万条）之前快速暴露逻辑错误。

用法:
  python tools/smoke_test.py <raw目录> <抽样条数>
然后:
  python run.py config_validate.yaml   （输出目录需指向抽样后的 raw）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


def main():
    if len(sys.argv) < 3:
        print("用法: python tools/smoke_test.py <raw目录> <抽样条数>")
        return 2
    raw = Path(sys.argv[1]); n = int(sys.argv[2])
    out = raw.parent / (raw.name + "_smoke")
    (out).mkdir(parents=True, exist_ok=True)

    c = pd.read_csv(raw / "comments.csv", dtype=str, low_memory=False)
    if len(c) > n:
        c = c.sample(n, random_state=42).sort_index()
    c.to_csv(out / "comments.csv", index=False, encoding="utf-8-sig")
    v = pd.read_csv(raw / "videos.csv", dtype=str, low_memory=False)
    v.to_csv(out / "videos.csv", index=False, encoding="utf-8-sig")
    print(f"抽样: comments={len(c)} videos={len(v)} -> {out}")
    print(f"请在 config_validate.yaml 中将 project.name 改为 '{out.name}' 对应输出，"
          f"并确认 raw 指向该目录（或直接用本脚本写入的 {out} 作为 raw）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
