#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_issue_label.py —— 回填历史期次「年 + 年内序号 + 总期号」双轨标签（一次性脚本）

背景（2026-11-22 邹苏煜定「年 + 期内序号 + 总期号」期号规则）：
  旧版期号只有纯递增「第 N 期」。新规则要求封面眉角 + footer 显式标
  「YYYY · 第 N 期 · 总第 N 期」。创刊年 2026，全年三码合一（年内序号 = 总期号），
  所以回填只是「加年份前缀 + 总期号后缀」。

范围：只回填第 10 期起（第 10 期才出现现行版式「第 N 期 · 把AI捡起来」+ footer 统一格式）。
      前 9 期是创刊初期旧版式（「第 1 期 · 拾光主笔」等口径），结构差异大、收益低，
      保持原样不动。

安全：用 Python 文件 IO 读改写，绝不走 shell cat/字符串传参（防 base64 大图被截断，
      见 memory「base64>100KB 禁 shell 传参」红线）。

用法：
  python3 backfill_issue_label.py            # 默认回填第 10 期起
  python3 backfill_issue_label.py --from 10  # 指定起始期号
  python3 backfill_issue_label.py --dry-run  # 只打印改动，不写盘
"""
import os, re, sys, glob, argparse

D = os.path.dirname(os.path.abspath(__file__))
FOUNDING_YEAR = 2026

def file_for_issue(n):
    """按期号找对应 HTML 文件。"""
    for f in glob.glob(os.path.join(D, f"*_第{n}期_AI视界.html")):
        return f
    return None

def backfill_one(n, dry_run):
    f = file_for_issue(n)
    if not f:
        print(f"⚠️ 第{n}期：找不到文件，跳过")
        return
    raw = open(f, encoding="utf-8").read()
    orig = raw

    # 1) 封面眉角 .meta：`第 N 期 · 把 AI 捡起来，学明白` → `YYYY · 第 N 期 · 总第 N 期`
    #    兼容有无空格两种写法（`第 10 期` vs `第10期`）
    meta_pat = re.compile(r'(<span class="meta">)\s*第\s*(\d+)\s*期[^<]*(</span>)')
    def meta_repl(m):
        n = int(m.group(2))
        return f'{m.group(1)}{FOUNDING_YEAR} · 第 {n} 期 · 总第 {n} 期{m.group(3)}'
    raw, meta_cnt = meta_pat.subn(meta_repl, raw)

    # 2) footer：`拾光 · AI 视界 · 第N期 · DATE` → `拾光 · AI 视界 · YYYY年第N期 · 总第N期 · DATE`
    def foot_repl(m):
        n = int(m.group(1))
        date = m.group(2)
        return f'拾光 · AI 视界 · {FOUNDING_YEAR}年第{n}期 · 总第{n}期 · {date}'
    foot_pat = re.compile(r'(?:拾光 · AI 视界 · )第\s*(\d+)\s*期\s*·\s*(\d{4}-\d{2}-\d{2})')
    raw, foot_cnt = foot_pat.subn(foot_repl, raw)

    if raw == orig:
        print(f"第{n}期：无可改处（可能已是新格式或非现行版式），跳过")
        return

    if dry_run:
        print(f"第{n}期（dry-run）：meta 改 {meta_cnt} 处、footer 改 {foot_cnt} 处")
    else:
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(raw)
        print(f"第{n}期：✅ meta {meta_cnt}、footer {foot_cnt}（{os.path.basename(f)}）")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=10, help="起始期号（默认 10）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 找全库最大期号
    files = glob.glob(os.path.join(D, "*_第*期_AI视界.html"))
    nums = []
    for f in files:
        m = re.match(r'.*_第(\d+)期_AI视界\.html', os.path.basename(f))
        if m:
            nums.append(int(m.group(1)))
    max_n = max(nums) if nums else 0

    print(f"回填范围：第 {args.start} 期 ~ 第 {max_n} 期（{'dry-run，不写盘' if args.dry_run else '实际写盘'}）")
    for n in range(args.start, max_n + 1):
        backfill_one(n, args.dry_run)

if __name__ == "__main__":
    main()
