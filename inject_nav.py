#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_nav.py —— 给期刊 HTML 注入「目录/侧边导航」+「全文站内搜索」

动机（2026-11-19）：期刊是静态 HTML，40+ 条长文无定位手段，读者只能从头滚到尾。
两个工具化能力，复用已有资产、零后端：

  1. 目录导航：左侧 sticky 目录树，动态从 .section（14 个栏目锚点）生成。
     点一下平滑滚到该栏目，滚动时高亮当前栏目（IntersectionObserver）。
  2. 全文搜索：feed.json（24 期全量结构化索引）由页面 fetch，客户端实时过滤
     「标题 + news + analysis」，跨期定位到具体条目，点击跳转到那一期的条目。

设计红线（与「段落级勿句级」的克制一致）：
  - 目录只到「栏目」级，不展开到每条 article —— 避免变成另一种「字幕感」。
  - 搜索只做「查 + 跳」，不做推荐/点赞/评论（要后端，做不到）。

用法：
  python3 inject_nav.py <期HTML或index.html>

注入位置：
  - CSS：</style> 前补 .toc 系列 + .searchbox 系列
  - 目录树 + 搜索框 HTML + JS：<div class="page"> 前插入

安全：幂等（已注入则跳过，--force 强刷）。找不到锚点/feed 时降级不报错。
"""

import os
import re
import sys

CSS = """
/* ====NAV-INJECT:CSS-START==== */
/* 目录侧边导航 + 全文搜索（工具化地基，2026-11-19） */
.toc{position:fixed;left:0;top:0;bottom:0;width:190px;background:#141414;border-right:1px solid #2a2a2a;z-index:900;overflow-y:auto;padding:52px 0 20px 0;font-family:'Microsoft YaHei','PingFang SC',sans-serif;}
.toc::-webkit-scrollbar{width:4px}
.toc::-webkit-scrollbar-thumb{background:#3a3a3a;border-radius:2px}
.toc-title{color:#8a8a8a;font-size:11px;letter-spacing:2px;padding:0 18px 8px;text-transform:uppercase;}
.toc a{display:flex;align-items:baseline;gap:8px;padding:7px 18px;color:#b8b0a0;text-decoration:none;font-size:13px;line-height:1.5;border-left:2px solid transparent;transition:all .15s ease;}
.toc a:hover{color:#fff;background:#1e1e1e;}
.toc a.active{color:#fff;background:#1e1e1e;border-left-color:#8a4a3a;font-weight:600;}
.toc a .no{color:#6a6a6a;font-size:11px;flex-shrink:0;font-variant-numeric:tabular-nums;}
.toc a.active .no{color:#a05a48;}
.toc a .cn{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
/* 移动端目录抽屉 */
.toc-toggle{display:none;position:fixed;right:14px;bottom:14px;width:44px;height:44px;border-radius:50%;background:#8a4a3a;color:#fff;border:none;font-size:18px;cursor:pointer;z-index:1100;box-shadow:0 4px 16px rgba(0,0,0,.4);}
/* 正文给左侧目录让位（仅宽屏） */
@media (min-width:1180px){
  .page{margin-left:190px !important;margin-right:auto !important;}
}
@media (max-width:1179px){
  .toc{transform:translateX(-100%);transition:transform .25s ease;}
  .toc.open{transform:translateX(0);}
  .toc-toggle{display:block;}
}
/* 搜索框 */
.searchbox{position:fixed;right:20px;top:12px;z-index:1100;width:280px;}
.searchbox input{width:100%;padding:8px 14px;background:#1e1e1e;border:1px solid #3a3a3a;border-radius:18px;color:#eee;font-size:13px;font-family:inherit;outline:none;}
.searchbox input:focus{border-color:#8a4a3a;}
.search-results{position:absolute;top:40px;left:0;right:0;background:#1a1a1a;border:1px solid #333;border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.5);max-height:420px;overflow-y:auto;display:none;}
.search-results.show{display:block;}
.search-results .sr-item{display:block;padding:10px 14px;border-bottom:1px solid #262626;color:#ccc;text-decoration:none;font-size:12px;line-height:1.5;}
.search-results .sr-item:hover{background:#222;}
.search-results .sr-item .sr-title{color:#eee;font-weight:600;font-size:13px;}
.search-results .sr-item .sr-meta{color:#888;font-size:11px;margin-top:3px;}
.search-results .sr-item .sr-snippet{color:#9a9a9a;font-size:12px;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.search-results .sr-empty{padding:20px;color:#777;font-size:12px;text-align:center;}
@media (max-width:720px){
  .searchbox{right:10px;top:10px;width:200px;}
}
/* ====NAV-INJECT:CSS-END==== */
"""


def build_nav():
    """生成目录树 + 搜索框的 HTML + JS。目录动态读 .section，搜索 fetch feed.json。"""
    return '''<!-- 目录侧边导航 -->
<div class="toc" id="tocNav">
  <div class="toc-title">本期目录</div>
  <div id="tocList"></div>
</div>
<button class="toc-toggle" id="tocToggle" onclick="toggleToc()" aria-label="目录">☰</button>
<!-- 全文搜索 -->
<div class="searchbox" id="searchBox">
  <input type="text" id="searchInput" placeholder="搜索往期内容… 如「光模块」" autocomplete="off" />
  <div class="search-results" id="searchResults"></div>
</div>
<script>
(function() {
  function init() {
  // ===== 目录导航：动态从 .section 生成 =====
  var tocList = document.getElementById('tocList');
  var sections = document.querySelectorAll('.section[id]');
  var seen = {};
  sections.forEach(function(sec) {
    var id = sec.id;
    if (!id || seen[id]) return;
    seen[id] = true;
    var head = sec.querySelector('.section-head');
    var no = head ? head.querySelector('.no') : null;
    var cn = head ? head.querySelector('.cn') : null;
    var noTxt = no ? no.textContent.trim() : '';
    var cnTxt = cn ? cn.textContent.trim() : (id || '');
    if (!cnTxt) return;
    var a = document.createElement('a');
    a.href = '#' + id;
    a.innerHTML = '<span class="no">' + noTxt + '</span><span class="cn">' + cnTxt + '</span>';
    a.addEventListener('click', function(e) {
      e.preventDefault();
      var target = document.getElementById(id);
      if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});
      // 移动端点完收起抽屉
      var toc = document.getElementById('tocNav');
      if (toc) toc.classList.remove('open');
    });
    tocList.appendChild(a);
  });

  // ===== 滚动高亮当前栏目（IntersectionObserver）=====
  var links = tocList.querySelectorAll('a');
  var byId = {};
  links.forEach(function(a) {
    var href = a.getAttribute('href');
    if (href && href.indexOf('#') === 0) byId[href.slice(1)] = a;
  });
  if ('IntersectionObserver' in window && Object.keys(byId).length) {
    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(en) {
        if (en.isIntersecting) {
          var a = byId[en.target.id];
          if (a) {
            links.forEach(function(l) { l.classList.remove('active'); });
            a.classList.add('active');
          }
        }
      });
    }, {rootMargin: '-20% 0px -70% 0px', threshold: 0});
    Object.keys(byId).forEach(function(id) {
      var el = document.getElementById(id);
      if (el) observer.observe(el);
    });
  }

  // ===== 移动端抽屉开关 =====
  window.toggleToc = function() {
    var toc = document.getElementById('tocNav');
    if (toc) toc.classList.toggle('open');
  };

  // ===== 全文搜索：fetch feed.json，客户端过滤 =====
  var feed = null;
  var feedLoaded = false;
  function loadFeed(cb) {
    if (feedLoaded) { cb(feed); return; }
    fetch('feed.json').then(function(r) { return r.json(); }).then(function(d) {
      feed = d; feedLoaded = true; cb(d);
    }).catch(function() { feedLoaded = true; feed = null; cb(null); });
  }
  // 建一个扁平索引：每期每篇文章一条记录
  function buildIndex(d) {
    var idx = [];
    if (!d || !d.issues) return idx;
    d.issues.forEach(function(issue) {
      (issue.articles || []).forEach(function(art) {
        idx.push({
          issue: issue.issue,
          date: issue.date,
          title: art.title || '',
          news: art.news || '',
          analysis: art.analysis || '',
          source: art.source || '',
          url: issue.url || ''
        });
      });
    });
    return idx;
  }
  var flatIndex = null;
  function ensureIndex(cb) {
    if (flatIndex) { cb(flatIndex); return; }
    loadFeed(function(d) {
      flatIndex = buildIndex(d);
      cb(flatIndex);
    });
  }
  function highlight(text, kw) {
    if (!kw) return text;
    var i = text.toLowerCase().indexOf(kw.toLowerCase());
    if (i < 0) return text.slice(0, 120);
    var s = Math.max(0, i - 30);
    var e = Math.min(text.length, i + kw.length + 60);
    var seg = (s > 0 ? '…' : '') + text.slice(s, e) + (e < text.length ? '…' : '');
    // 转义 + 简单高亮
    seg = seg.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var idx = seg.toLowerCase().indexOf(kw.toLowerCase());
    if (idx >= 0) {
      seg = seg.slice(0, idx) + '<mark>' + seg.slice(idx, idx + kw.length) + '</mark>' + seg.slice(idx + kw.length);
    }
    return seg;
  }
  var searchInput = document.getElementById('searchInput');
  var searchResults = document.getElementById('searchResults');
  var searchTimer = null;
  searchInput.addEventListener('input', function() {
    var q = searchInput.value.trim();
    if (searchTimer) clearTimeout(searchTimer);
    if (!q) { searchResults.classList.remove('show'); return; }
    searchTimer = setTimeout(function() {
      ensureIndex(function(idx) {
        if (!idx.length) {
          searchResults.innerHTML = '<div class="sr-empty">未加载到内容数据（feed.json）</div>';
          searchResults.classList.add('show');
          return;
        }
        var ql = q.toLowerCase();
        var hits = [];
        idx.forEach(function(it) {
          var hay = (it.title + ' ' + it.news + ' ' + it.analysis).toLowerCase();
          if (hay.indexOf(ql) >= 0) hits.push(it);
        });
        // 标题命中优先
        hits.sort(function(a, b) {
          var at = a.title.toLowerCase().indexOf(ql) >= 0 ? 0 : 1;
          var bt = b.title.toLowerCase().indexOf(ql) >= 0 ? 0 : 1;
          if (at !== bt) return at - bt;
          return b.issue - a.issue; // 同期优先最近
        });
        hits = hits.slice(0, 30);
        if (!hits.length) {
          searchResults.innerHTML = '<div class="sr-empty">没有找到「' + q.replace(/</g, '&lt;') + '」相关的内容</div>';
        } else {
          searchResults.innerHTML = hits.map(function(it) {
            var snippet = highlight(it.news || it.analysis || '', q);
            return '<a class="sr-item" href="' + (it.url || '') + '" target="_self">' +
              '<div class="sr-title">' + it.title.replace(/</g, '&lt;') + '</div>' +
              '<div class="sr-meta">第 ' + it.issue + ' 期 · ' + it.date + ' · ' + it.source.replace(/</g, '&lt;') + '</div>' +
              '<div class="sr-snippet">' + snippet + '</div>' +
              '</a>';
          }).join('');
        }
        searchResults.classList.add('show');
      });
    }, 250);
  });
  // 点页面其它地方收起搜索结果
  document.addEventListener('click', function(e) {
    if (searchResults && !searchResults.contains(e.target) && e.target !== searchInput) {
      searchResults.classList.remove('show');
    }
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && searchResults) searchResults.classList.remove('show');
  });
  } // end init
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>
'''


def remove_old(raw):
    """删除旧版注入（CSS 标记块 + 目录树 div + searchbox + script），幂等。"""
    changed = False
    # 删标记包裹的 CSS
    raw2, n = re.subn(
        r'/\* ====NAV-INJECT:CSS-START==== \*/.+?/\* ====NAV-INJECT:CSS-END==== \*/',
        '', raw, flags=re.DOTALL)
    if n:
        raw = raw2
        changed = True
    # 删目录树 + toggle + searchbox + script（从注释标记到 </script>）
    raw2, n = re.subn(
        r'<!-- 目录侧边导航 -->.*?</script>',
        '', raw, flags=re.DOTALL)
    if n:
        raw = raw2
        changed = True
    return raw, changed


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("html_path", help="期 HTML 或 index.html")
    ap.add_argument("--force", action="store_true", help="强制重新注入")
    args = ap.parse_args()

    raw = open(args.html_path, encoding="utf-8").read()

    has_nav = 'id="tocNav"' in raw or 'id="searchBox"' in raw
    if has_nav and not args.force:
        print("⚠️ 该 HTML 已有目录/搜索，跳过。（用 --force 强制重新注入）")
        return
    if has_nav and args.force:
        raw, removed = remove_old(raw)
        if removed:
            print("⚠️ 已删除旧目录/搜索（--force）")

    if '</style>' not in raw:
        print("❌ 找不到 </style>，无法注入 CSS。")
        sys.exit(1)
    raw = raw.replace('</style>', CSS + '</style>', 1)

    if '<div class="page">' not in raw:
        print("❌ 找不到 <div class=\\\"page\\\">，无法注入。")
        sys.exit(1)
    nav = build_nav()
    raw = raw.replace('<div class="page">', nav + '\\n<div class="page">', 1)

    open(args.html_path, "w", encoding="utf-8").write(raw)
    print(f"✅ 已注入目录导航 + 全文搜索 → {args.html_path}")


if __name__ == "__main__":
    main()
