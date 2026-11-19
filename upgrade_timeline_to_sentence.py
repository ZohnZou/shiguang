#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upgrade_timeline_to_sentence.py —— 把「片段级时间轴」升级成「句子级时间轴」（逐句跟踪用）

原理：合成保持片段级（时间不爆），但时间轴细化到句——
  读片段目录（拿每个片段的朗读文本）+ 已有的片段级时间轴（拿每个片段的 start/end），
  用「句字数比例」把片段时长插值分配到句，产出句子级时间轴。

这样不用重新合成音频（省 25 分钟），直接就地把 44 条片段级 → 672 句句级。

用法：
  python3 upgrade_timeline_to_sentence.py --issue 24 --dir 本期片段
  读 audio/第N期_时间轴.json（片段级）→ 写回同一文件（句子级，覆盖）

安全：片段级时间轴必须存在；插值后句总数 > 片段数才写入。
"""
import os, sys, json, glob, re, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tts_issue import parse_fragment, build_speech_units, interpolate_sentence_timeline

D = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(D, "audio")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=int, required=True)
    ap.add_argument("--dir", default=os.path.join(D, "本期片段"))
    args = ap.parse_args()

    tl_path = os.path.join(AUDIO_DIR, f"第{args.issue}期_时间轴.json")
    if not os.path.exists(tl_path):
        print(f"❌ 片段级时间轴不存在: {tl_path}")
        sys.exit(1)

    frag_tl = json.load(open(tl_path, encoding="utf-8"))

    # 幂等防护：若输入已是句子级（含 sentenceText 字段），拒绝重复升级（否则双重插值爆炸）
    if frag_tl and "sentenceText" in frag_tl[0]:
        print(f"⚠️ 该时间轴已是句子级（{len(frag_tl)} 句，含 sentenceText），无需重复升级。")
        sys.exit(0)

    # 读片段，构建「sort -> 朗读文本」映射
    frags = [parse_fragment(f) for f in sorted(glob.glob(os.path.join(args.dir, "*.md")))]
    units = build_speech_units(frags)
    sort2text = {u[0]: u[3] for u in units}  # sort -> 朗读文本

    # 逐片段插值出句子级时间轴
    sentence_tl = []
    for f in frag_tl:
        sort = f["sort"]
        text = sort2text.get(sort, "")
        if not text:
            continue
        dur = f["end"] - f["start"]
        sents = interpolate_sentence_timeline(sort, f["col"], f["title"], text, f["start"], dur)
        sentence_tl.extend(sents)

    print(f"片段级: {len(frag_tl)} 条 → 句子级: {len(sentence_tl)} 句")

    if len(sentence_tl) <= len(frag_tl):
        print("❌ 插值后句数没有超过片段数，异常，不写入。")
        sys.exit(1)

    # 校验：end 递增、无倒序
    prev = 0
    for i, s in enumerate(sentence_tl):
        if s["start"] < prev - 0.5:
            print(f"❌ 第{i}句 start={s['start']} 早于前一句 end={prev}，异常。")
            sys.exit(1)
        prev = s["end"]

    with open(tl_path, "w", encoding="utf-8") as f:
        json.dump(sentence_tl, f, ensure_ascii=False, indent=2)

    total = sentence_tl[-1]["end"]
    print(f"✅ 已升级为句子级时间轴: {tl_path}")
    print(f"   {len(sentence_tl)} 句，总时长 {total/60:.1f} 分钟")


if __name__ == "__main__":
    main()
