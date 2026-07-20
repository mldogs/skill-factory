#!/usr/bin/env python3
"""
build_page.py — рендер podcasts/<slug>/<slug>.html из podcast.json (+ i18n/).

stdlib-only. Самодостаточная двуязычная (RU/EN) страница: standalone-шапка
(название подкаста + переключатель RU/EN), ростер спикеров, тайм-лайн
YouTube-глав с deep-link, секции с
карточками концептов (inline SVG/CSS визуалы), блок «Споры», поиск по глоссарию,
Q&A на <details>. Картинки — по относительному пути из assets/.

Использование:
  python3 build_page.py [podcasts/<slug>]   # без аргумента — пересобрать все podcasts/*/
"""
import html
import json
import os
import re
import sys
from urllib.parse import unquote, urlparse


# ---------- root / discovery ----------

def find_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(d, ".env")) or \
           os.path.isdir(os.path.join(d, "podcasts")) or \
           os.path.isdir(os.path.join(d, "books")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            return os.path.abspath(start or os.getcwd())
        d = nd


def e(s):
    return html.escape(s or "", quote=True)


# ---------- load + i18n merge ----------

def load(pdir):
    p = json.load(open(os.path.join(pdir, "podcast.json"), encoding="utf-8"))
    i18n_dir = os.path.join(pdir, "i18n")
    gl = {}
    gpath = os.path.join(i18n_dir, "_global.json")
    if os.path.isfile(gpath):
        gl = json.load(open(gpath, encoding="utf-8"))

    ep = p["episode"]
    ep["title_en_disp"] = ep.get("title_en") or ep.get("title_ru")
    ep["summary_en"] = gl.get("summary_en") or ep.get("summary_ru")

    # speakers EN bios
    sp_en = {x["id"]: x for x in gl.get("speakers", [])}
    for s in p.get("speakers", []):
        s["bio_en"] = sp_en.get(s["id"], {}).get("bio_en") or s.get("bio_ru")

    # sections + concepts EN
    for sec in p.get("sections", []):
        spath = os.path.join(i18n_dir, sec["id"] + ".json")
        tr = json.load(open(spath, encoding="utf-8")) if os.path.isfile(spath) else {}
        sec["intro_en"] = tr.get("intro_en") or sec.get("intro_ru")
        cmap = {c["id"]: c for c in tr.get("concepts", [])}
        for c in sec.get("concepts", []):
            ct = cmap.get(c["id"], {})
            c["explanation_en"] = ct.get("explanation_en") or c.get("explanation_ru")
            c["analogy_en"] = ct.get("analogy_en") or c.get("analogy_ru")
            c["visual_title_en"] = ct.get("visual_title_en") or c["visual"].get("title_ru")
            c["tldr_en"] = ct.get("tldr_en") or c.get("tldr_ru")
            c["key_points_en"] = ct.get("key_points_en") or c.get("key_points_ru") or []

    # glossary / qa EN
    gmap = {g["term_en"]: g for g in gl.get("glossary", [])}
    for g in p.get("glossary", []):
        g["definition_en"] = gmap.get(g["term_en"], {}).get("definition_en") or g.get("definition_ru")
    qmap = {q["id"]: q for q in gl.get("qa", [])}
    for q in p.get("qa_seeds", []):
        qt = qmap.get(q["id"], {})
        q["question_en"] = qt.get("question_en") or q.get("question_ru")
        q["points_en"] = qt.get("expected_answer_points_en") or q.get("expected_answer_points")

    # debates EN
    dmap = {d["id"]: d for d in gl.get("debates", [])}
    for d in p.get("debates", []):
        dt = dmap.get(d["id"], {})
        d["topic_en"] = dt.get("topic_en") or d.get("topic_ru")
        d["resolution_en"] = dt.get("resolution_en") or d.get("resolution_ru")
        pos_en = dt.get("positions", [])
        for i, pos in enumerate(d.get("positions", [])):
            pos["claim_en"] = pos_en[i].get("claim_en") if i < len(pos_en) else pos.get("claim_ru")
    return p


# ---------- bilingual helper ----------

def L(ru, en=None):
    """пара <span class=lang ru/en>"""
    en = en if en is not None else ru
    return ('<span class="lang ru">%s</span><span class="lang en">%s</span>'
            % (e(ru), e(en)))


_MARK = re.compile(r"\[\[([^|\]]+)\|([^\]]*)\]\]")


def strip_markup(text):
    """[[term|gloss]] -> term (для EN-фолбэка / чистого текста)."""
    return _MARK.sub(r"\1", text or "")


def ru_markup(text):
    """RU-текст: [[term|перевод]] -> <span class=term data-tip=перевод> с подсказкой; остальное экранируется."""
    if not text:
        return ""
    out, pos = [], 0
    for m in _MARK.finditer(text):
        out.append(e(text[pos:m.start()]))
        out.append('<span class="term" tabindex="0" data-tip="%s">%s</span>'
                    % (e(m.group(2).strip()), e(m.group(1).strip())))
        pos = m.end()
    out.append(e(text[pos:]))
    return "".join(out)


def Lc(ru, en=None):
    """двуязычный КОНТЕНТ: RU может нести разметку [[term|перевод]] (tooltip), EN — простой текст."""
    en = en if en is not None else strip_markup(ru)
    return ('<span class="lang ru">%s</span><span class="lang en">%s</span>'
            % (ru_markup(ru), e(en)))


def yt(vid, t):
    base = "https://www.youtube.com/watch?v=" + e(vid)
    if t is not None:
        base += "&t=%ds" % int(t)
    return base


def hhmmss(sec):
    if sec is None:
        return ""
    sec = int(sec)
    if sec >= 3600:
        return "%d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)
    return "%d:%02d" % (sec // 60, sec % 60)


def source_label(source):
    """Build a compact human label from a source URL/path."""
    raw = (source or "").strip()
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    tail = unquote((parsed.path or "").rstrip("/").split("/")[-1])
    tail = re.sub(r"\.(?:html?|pdf|md|txt)$", "", tail, flags=re.I)
    tail = re.sub(r"[-_]+", " ", tail).strip()
    if tail.lower() in ("", "index", "home"):
        tail = ""
    if host and tail:
        label = "%s · %s" % (host, tail)
    else:
        label = host or tail or raw
    return label[:72] + ("…" if len(label) > 72 else "")


def render_source_docs(source_docs):
    links, seen = [], set()
    for source in source_docs or []:
        if not isinstance(source, str):
            continue
        source = source.strip()
        if not source or source in seen:
            continue
        seen.add(source)
        label = source_label(source)
        parsed = urlparse(source)
        if parsed.scheme in ("http", "https"):
            links.append('<a class="evidence-link" href="%s" target="_blank" rel="noopener" title="%s">%s ↗</a>'
                         % (e(source), e(source), e(label)))
        else:
            links.append('<span class="evidence-link">%s</span>' % e(label))
    if not links:
        return ""
    return ('<div class="evidence-links"><span class="evidence-label">%s</span>%s</div>'
            % (L("Доказательства", "Evidence"), "".join(links)))


def article_network_visual():
    """Poster-scale dossier/network illustration; CSS drives the line drawing."""
    return '''
<div class="article-network" aria-hidden="true">
  <svg viewBox="0 0 760 620" focusable="false">
    <g class="dossier-rule">
      <path d="M52 74H708M52 548H708M112 38V584M650 38V584"/>
      <path d="M52 182H112M650 426H708M314 74V120M486 500V548"/>
    </g>
    <g class="network-lines">
      <path class="network-line nl-1" pathLength="1" d="M148 178C238 116 306 118 378 194S514 300 622 244"/>
      <path class="network-line nl-2" pathLength="1" d="M148 178C204 266 244 330 342 350S506 352 592 454"/>
      <path class="network-line nl-3" pathLength="1" d="M378 194C384 282 380 318 342 350"/>
      <path class="network-line nl-4" pathLength="1" d="M622 244C578 316 552 368 592 454"/>
      <path class="network-line nl-5" pathLength="1" d="M342 350C432 412 486 436 592 454"/>
      <path class="network-line nl-6 signal" pathLength="1" d="M148 178L622 244L342 350L592 454"/>
    </g>
    <g class="network-node node-a" transform="translate(148 178)">
      <circle r="34"/><circle class="node-core" r="7"/>
      <path d="M-14-45H25M-14 45H12"/>
      <text x="-26" y="-52">A/01</text>
    </g>
    <g class="network-node node-b" transform="translate(378 194)">
      <rect x="-41" y="-30" width="82" height="60"/>
      <circle class="node-core" r="7"/>
      <text x="-34" y="-42">SRC/02</text>
    </g>
    <g class="network-node node-c" transform="translate(622 244)">
      <circle r="27"/><circle class="node-core" r="7"/>
      <text x="-48" y="-39">SIG/03</text>
    </g>
    <g class="network-node node-d" transform="translate(342 350)">
      <path d="M0-40L39 28H-39Z"/><circle class="node-core" r="7"/>
      <text x="-37" y="52">RISK/04</text>
    </g>
    <g class="network-node node-e" transform="translate(592 454)">
      <rect x="-32" y="-32" width="64" height="64" transform="rotate(45)"/>
      <circle class="node-core" r="7"/>
      <text x="-44" y="58">OUT/05</text>
    </g>
    <g class="dossier-seal" transform="translate(158 468)">
      <circle r="72"/><circle r="55"/><path d="M-34 0H34M0-34V34"/>
      <text x="-47" y="94">VERIFIED</text>
    </g>
    <g class="dossier-index">
      <text x="56" y="60">DOSSIER // EVIDENCE NETWORK</text>
      <text x="654" y="570">FIG. 01</text>
    </g>
  </svg>
</div>'''


# ---------- inline SVG/CSS visual components ----------
# Подписи языко-нейтральны (коротко/цифрами); смысл несёт двуязычный caption.
# SVG-компоненты используют общий помощник переноса (_wrap/_txtml): SVG <text>
# сам не переносится, поэтому любая подпись длиннее maxch режется на tspan-ы.

def _labels(params, n, default):
    p = (params or {}).get("labels")
    if isinstance(p, list) and p:
        out = [str(x) for x in p][:n]
    else:
        out = list(default)[:n]
    while len(out) < n:
        out.append("")
    return out


def _svg(body, vb="0 0 320 168"):
    return '<svg viewBox="%s" class="viz vz" role="img" aria-hidden="true">%s</svg>' % (vb, body)


def _txt(x, y, s, cls="lbl", anchor="middle"):
    return '<text x="%s" y="%s" text-anchor="%s" class="%s">%s</text>' % (x, y, anchor, cls, e(str(s)))


def _wrap(s, maxch):
    """Greedy word-wrap into <=3 short lines (SVG <text> never wraps itself)."""
    words, lines, cur = (s or "").split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > maxch:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines[:3]


def _txtml(x, y, s, maxch=16, cls="lbl", anchor="middle", lh=12):
    """Multi-line _txt: wraps long labels into tspans, block centred on y."""
    lines = _wrap(str(s), maxch)
    if len(lines) <= 1:
        return _txt(x, y, s, cls=cls, anchor=anchor)
    y0 = y - (len(lines) - 1) * lh // 2
    spans = "".join('<tspan x="%s" y="%s">%s</tspan>' % (x, y0 + i * lh, e(t))
                    for i, t in enumerate(lines))
    return '<text text-anchor="%s" class="%s">%s</text>' % (anchor, cls, spans)


def v_define(params, c):
    return ('<div class="v-define"><div class="v-define-term">%s</div>'
            '<div class="v-define-line"></div></div>') % e(c["term_en"])


def v_layers(params, c):
    labs = _labels(params, 5, ["", "", "", "", ""])
    labs = [x for x in labs if x] or ["L1", "L2", "L3"]
    rows = "".join('<div class="v-layer" style="--i:%d">%s</div>' % (i, e(x))
                   for i, x in enumerate(labs))
    return '<div class="v-layers">%s</div>' % rows


def v_cycle(params, c):
    # labelled loop: params.nodes (или labels) подписывают узлы вокруг кольца;
    # длинные подписи переносятся и растут наружу от кольца, не пересекая его
    import math
    p = params or {}
    labs = [str(x) for x in (p.get("nodes") or p.get("labels") or []) if x][:6]
    cx, cy, r = 180, 100, 46
    body = ('<circle cx="180" cy="100" r="46" class="loopring"/>'
            '<path d="M180,54 A46,46 0 1 1 140,122" class="loopdash"/>'
            '<path d="M144,112 l-6,12 l13,-2" class="arrhead"/>')
    ring = labs if labs else ["", "", "", ""]
    n = max(len(ring), 1)
    for i, lab in enumerate(ring):
        a = math.radians(-90 + i * 360.0 / n)
        c_, s_ = math.cos(a), math.sin(a)
        x, y = cx + r * c_, cy + r * s_
        body += '<circle cx="%.1f" cy="%.1f" r="7" class="node"/>' % (x, y)
        if lab:
            lx, ly = cx + 66 * c_, cy + 66 * s_ + 4
            anchor = "start" if c_ > 0.35 else ("end" if c_ < -0.35 else "middle")
            body += _txtml(round(lx, 1), round(ly, 1), lab, maxch=16, anchor=anchor, lh=11)
    return _svg(body, vb="0 0 360 200")


def v_steps(params, c):
    labs = _labels(params, 6, [])
    labs = [x for x in labs if x] or ["1", "2", "3"]
    cells = "".join(
        '<div class="v-step"><span class="v-step-n">%d</span><span class="v-step-l">%s</span></div>'
        % (i + 1, e(x)) for i, x in enumerate(labs))
    return '<div class="v-steps">%s</div>' % cells


def v_tug(params, c):
    a, b = _labels(params, 2, ["A", "B"])
    return ('<div class="v-tug"><span class="v-tug-a">%s</span>'
            '<span class="v-tug-rope">⟷</span><span class="v-tug-b">%s</span></div>'
            % (e(a or "A"), e(b or "B")))


def v_two_targets(params, c):
    a, b = _labels(params, 2, ["old", "new"])
    return ('<div class="v-two"><div class="v-two-old">%s</div>'
            '<div class="v-two-arrow">→</div><div class="v-two-new">%s</div></div>'
            % (e(a or "old"), e(b or "new")))


def v_funnel(params, c):
    # до 5 ступеней; ширина сужается к минимуму 40%, текст переносится (HTML)
    labs = [x for x in _labels(params, 5, ["", "", ""]) if x] or ["", "", ""]
    n = len(labs)
    step = 60.0 / max(1, n - 1)
    rows = "".join('<div class="v-funnel-r" style="--w:%d%%">%s</div>'
                   % (round(100 - i * step), e(x)) for i, x in enumerate(labs))
    return '<div class="v-funnel">%s</div>' % rows


def v_timeline(params, c):
    # vertical layout: подписи любой длины переносятся рядом со своей точкой
    # и не могут столкнуться (горизонтальный вариант ломался на длинных фразах)
    labs = _labels(params, 6, [])
    labs = [x for x in labs if x] or ["now", "→", "future"]
    rows = "".join(
        '<div class="v-tl-row"><span class="v-tl-dot"></span><span class="v-tl-l">%s</span></div>'
        % e(x) for x in labs)
    return '<div class="v-tl">%s</div>' % rows


def v_many_to_one(params, c):
    labs = _labels(params, 4, ["", "", "", ""])
    srcs = [x for x in labs if x] or ["a", "b", "c"]
    rows = "".join(
        '<line x1="6" y1="%d" x2="78" y2="60" class="m2o-l"/>'
        '<circle cx="6" cy="%d" r="6" class="m2o-s"/>'
        % (16 + i * 30, 16 + i * 30) for i in range(len(srcs)))
    return ('<svg viewBox="0 0 120 120" class="viz">%s'
            '<circle cx="90" cy="60" r="16" class="m2o-hub"/>'
            '<text x="90" y="64" class="m2o-t">1</text></svg>' % rows)


def v_split(params, c):
    # два режима: rich (left_title/left_items + right_title/right_items) или
    # простая пара labels; HTML — текст любой длины переносится сам
    p = params or {}
    if p.get("left_items") or p.get("right_items"):
        def col(title, items, side):
            lis = "".join('<li>%s</li>' % e(str(x)) for x in (items or []))
            t = '<div class="v-split-t">%s</div>' % e(str(title)) if title else ""
            return '<div class="v-split-c v-split-%s">%s<ul>%s</ul></div>' % (side, t, lis)
        return ('<div class="v-split">%s%s</div>'
                % (col(p.get("left_title"), p.get("left_items"), "l"),
                   col(p.get("right_title"), p.get("right_items"), "r")))
    a, b = _labels(params, 2, ["", ""])
    return ('<div class="v-split"><div class="v-split-c">%s</div>'
            '<div class="v-split-c">%s</div></div>' % (e(a), e(b)))


def v_gauge(params, c):
    # value-driven: дуга заполнения и стрелка считаются из ОДНОГО угла и всегда
    # согласованы (старые фиксированные координаты расходились при увеличении)
    import math
    p = params or {}
    try:
        val = float(p.get("value"))
    except (TypeError, ValueError):
        val = 0.62
    if val > 1:  # допускаем value в единицах params.max (например 70 из 100)
        try:
            mx = float(p.get("max") or 100)
        except (TypeError, ValueError):
            mx = 100
        val = val / (mx if mx >= val else 100)
    val = min(0.95, max(0.05, val))
    cx, cy, r = 160, 130, 120
    ang = math.pi * (1 - val)
    ex, ey = cx + r * math.cos(ang), cy - r * math.sin(ang)
    nx, ny = cx + (r - 22) * math.cos(ang), cy - (r - 22) * math.sin(ang)
    body = ('<path d="M40,130 A120,120 0 0 1 280,130" class="gaugebg"/>'
            '<path d="M40,130 A120,120 0 0 1 %.1f,%.1f" class="gaugefill"/>'
            '<line x1="160" y1="130" x2="%.1f" y2="%.1f" class="needle"/>'
            '<circle cx="160" cy="130" r="7" class="pivot"/>') % (ex, ey, nx, ny)
    body += (_txtml(16, 150, p.get("left", ""), maxch=18, anchor="start")
             + _txtml(304, 150, p.get("right", ""), maxch=18, anchor="end"))
    return _svg(body, vb="0 0 320 162")


def v_flow(params, c):
    # горизонтальная цепочка 2–4 боксов со стрелками; ширины подгоняются под текст
    p = params or {}
    steps = [str(x) for x in (p.get("steps") or p.get("labels") or ["in", "process", "out"]) if x][:4]
    widths = [max(56, 7 * len(t) + 16) for t in steps]
    gap = 26
    total = sum(widths) + gap * (len(widths) - 1)
    W = max(320, total + 24)
    x0 = (W - total) // 2
    body = ""
    for i, (t, w) in enumerate(zip(steps, widths)):
        body += '<rect x="%d" y="38" width="%d" height="30" rx="7" class="box"/>' % (x0, w)
        body += _txt(x0 + w // 2, 58, t)
        if i < len(steps) - 1:
            ax = x0 + w
            body += ('<line x1="%d" y1="53" x2="%d" y2="53" class="edge"/>'
                     '<path d="M%d,53 l-7,-4 v8 Z" class="arrowh"/>') % (ax + 4, ax + gap - 4, ax + gap - 4)
        x0 += w + gap
    return _svg(body, vb="0 0 %d 106" % W)


def v_stack(params, c):
    # 2–4 слоя; params.hot (index) подсвечивает один
    p = params or {}
    layers = [str(x) for x in (p.get("layers") or p.get("labels") or ["top", "middle", "base"]) if x][:4]
    hot = p.get("hot", -1)
    n = len(layers)
    H = 24 + n * 38 + 6
    body = ""
    for i, t in enumerate(layers):
        y = 18 + i * 38
        cls = "box hot" if i == hot else "box"
        body += '<rect x="60" y="%d" width="200" height="30" rx="7" class="%s"/>' % (y, cls)
        body += _txtml(160, y + 20, t, maxch=26, lh=11)
    return _svg(body, vb="0 0 320 %d" % H)


def v_bars(params, c):
    # 2–4 подписанных столбца, value 0..1, флаг good красит; шаг между столбцами
    # и ширина viewBox выводятся из самой длинной строки подписи — подписи не
    # сталкиваются и не режутся краем
    p = params or {}
    items = (p.get("items") or [{"label": "a", "value": 0.4}, {"label": "b", "value": 0.8}])[:4]
    n = len(items)
    wrapped = [_wrap(str(it.get("label", "")), 12) for it in items]
    maxline = max((len(ln) for ls in wrapped for ln in ls), default=4)
    pitch = max(92, int(6.4 * maxline) + 12)
    bw = 54
    total = n * pitch
    W = max(320, total + 24)
    x0 = (W - total) // 2 + (pitch - bw) // 2
    body = '<line x1="%d" y1="118" x2="%d" y2="118" class="axis"/>' % (
        (W - total) // 2, (W - total) // 2 + total)
    for i, it in enumerate(items):
        try:
            v = min(1.0, max(0.05, float(it.get("value", 0.5))))
        except (TypeError, ValueError):
            v = 0.5
        h = int(84 * v)
        x = x0 + i * pitch
        good = it.get("good")
        cls = "barfill good" if good is True else ("barfill bad" if good is False else "barfill")
        body += ('<rect x="%d" y="%d" width="%d" height="%d" rx="4" class="%s" '
                 'style="transform-origin:%dpx 118px;animation-delay:%dms"/>'
                 % (x, 118 - h, bw, h, cls, x + bw // 2, i * 140))
        body += _txtml(x + bw // 2, 134, it.get("label", ""), maxch=12, lh=11)
    return _svg(body, vb="0 0 %d 162" % W)


def v_venn(params, c):
    # два пересекающихся множества; подписи сторон — ПОД кругами
    p = params or {}
    body = ('<circle cx="120" cy="72" r="50" class="venn"/>'
            '<circle cx="200" cy="72" r="50" class="venn b"/>'
            + _txtml(96, 140, p.get("left", "A"), maxch=14, lh=11)
            + _txtml(224, 140, p.get("right", "B"), maxch=14, lh=11)
            + _txtml(160, 74, p.get("mid", ""), maxch=10, cls="lbl sm", lh=10))
    return _svg(body, vb="0 0 320 168")


def v_orbit(params, c):
    # спутники вокруг ядра
    import math
    p = params or {}
    center = p.get("center", "core")
    sats = [str(x) for x in (p.get("sats") or p.get("labels") or ["a", "b", "c"]) if x][:5]
    cy = 96
    body = ('<circle cx="160" cy="96" r="48" class="orbitring"/>'
            '<circle cx="160" cy="96" r="24" class="corehub"/>'
            + _txtml(160, 100, center, maxch=8, lh=11))
    n = max(len(sats), 1)
    for i, t in enumerate(sats):
        a = math.radians(-90 + i * 360.0 / n)
        x, y = 160 + 48 * math.cos(a), cy + 48 * math.sin(a)
        lx, ly = 160 + 74 * math.cos(a), cy + 74 * math.sin(a)
        anchor = "middle" if abs(math.cos(a)) < 0.4 else ("start" if math.cos(a) > 0 else "end")
        body += '<circle cx="%.1f" cy="%.1f" r="8" class="node" style="animation-delay:%dms"/>' % (x, y, i * 150)
        body += _txtml(round(lx, 1), round(ly + 4, 1), t, maxch=14, anchor=anchor, lh=11)
    return _svg(body, vb="0 0 320 190")


def v_shield(params, c):
    # ядро под концентрическими дугами защиты
    p = params or {}
    core = str(p.get("core", "core"))
    rings = [str(x) for x in (p.get("rings") or p.get("labels") or ["guard"]) if x][:3]
    cw = max(72, 7 * len(core) + 18)
    body = ('<rect x="%d" y="112" width="%d" height="30" rx="7" class="box hot"/>' % (160 - cw // 2, cw)
            + _txt(160, 132, core))
    for i, t in enumerate(rings):
        r = 58 + i * 26
        body += ('<path d="M%d,128 A%d,%d 0 0 1 %d,128" class="shieldarc" '
                 'style="animation-delay:%dms"/>' % (160 - r, r, r, 160 + r, i * 160))
        body += _txt(160, 122 - r, t, cls="lbl sm")
    return _svg(body, vb="0 0 320 150")


def v_matrix2(params, c):
    # квадрант 2×2; params.mark = 1..4 (TL, TR, BL, BR) ставит точку
    p = params or {}
    body = ('<rect x="70" y="24" width="180" height="104" rx="8" class="pane"/>'
            '<line x1="160" y1="24" x2="160" y2="128" class="line2"/>'
            '<line x1="70" y1="76" x2="250" y2="76" class="line2"/>')
    mark = p.get("mark", 2)
    mx = 115 if mark in (1, 3) else 205
    my = 50 if mark in (1, 2) else 102
    body += '<circle cx="%d" cy="%d" r="8" class="hit"/>' % (mx, my)
    body += (_txtml(60, 54, p.get("y_high", ""), maxch=9, anchor="end", cls="lbl sm", lh=10)
             + _txtml(60, 106, p.get("y_low", ""), maxch=9, anchor="end", cls="lbl sm", lh=10)
             + _txtml(115, 144, p.get("x_left", ""), maxch=13, cls="lbl sm", lh=10)
             + _txtml(205, 144, p.get("x_right", ""), maxch=13, cls="lbl sm", lh=10))
    return _svg(body, vb="0 0 320 158")


def v_loop_gate(params, c):
    # цикл итераций, каждый оборот проходит через ворота-чекпойнт
    p = params or {}
    gate = str(p.get("gate", "verify"))
    gw = max(64, 7 * len(gate) + 20)
    body = ('<path d="M160,36 A48,48 0 1 1 159.9,36" class="loopring"/>'
            '<path d="M120,52 l-4,12 l13,-4" class="arrhead"/>'
            + '<rect x="%d" y="118" width="%d" height="28" rx="6" class="gatebox"/>' % (160 - gw // 2, gw)
            + _txt(160, 137, gate)
            + _txtml(160, 82, p.get("loop", "iterate"), maxch=12, lh=11))
    return _svg(body, vb="0 0 320 152")


VIZ = {
    "define": v_define, "layers": v_layers, "cycle": v_cycle, "steps": v_steps,
    "tug": v_tug, "two_targets": v_two_targets, "funnel": v_funnel,
    "timeline": v_timeline, "many_to_one": v_many_to_one, "split": v_split, "gauge": v_gauge,
    "flow": v_flow, "stack": v_stack, "bars": v_bars, "venn": v_venn,
    "orbit": v_orbit, "shield": v_shield, "matrix2": v_matrix2, "loop_gate": v_loop_gate,
}


def render_visual(pdir, c):
    v = c["visual"]
    typ = v.get("type")
    if typ == "image" and v.get("cache_filename"):
        fp = os.path.join(pdir, v["cache_filename"])
        if os.path.isfile(fp):
            return '<img class="v-img" src="%s" alt="%s">' % (e(v["cache_filename"]), e(v.get("alt_ru")))
    comp = v.get("component")
    fn = VIZ.get(comp)
    if fn:
        try:
            return fn(v.get("params"), c)
        except Exception as exc:  # диаграмма не должна ломать сборку — но и не молчать
            return '<!-- viz error %s: %s -->%s' % (e(c.get("id", "?")), e(str(exc)), v_define(None, c))
    # fallback: нейтральная карточка с термином
    return v_define(None, c)


# ---------- page sections ----------

def nav_html(brand):
    """Standalone header: episode/podcast name as brandmark + RU/EN toggle."""
    return ('<header class="bar"><span class="brandmark" title="%s">%s</span>'
            '<span class="spacer"></span>'
            '<button id="langToggle" class="lang-toggle" type="button">EN</button></header>'
            % (e(brand), e(brand)))


def render_roster(speakers, article_mode=False):
    cards = []
    for s in speakers:
        initials = "".join(w[0] for w in s["name"].split()[:2]).upper()
        if article_mode:
            role_ru = "red team" if s["role"] == "host" else "автор"
            role_en = "red team" if s["role"] == "host" else "author"
        else:
            role_ru = "ведущий" if s["role"] == "host" else "гость"
            role_en = "host" if s["role"] == "host" else "guest"
        cards.append(
            '<div class="spk"><div class="spk-mono spk-%s">%s</div>'
            '<div class="spk-body"><div class="spk-name">%s <span class="spk-role">%s</span></div>'
            '<div class="spk-bio">%s</div></div></div>'
            % (s["role"], e(initials), e(s["name"]), L(role_ru, role_en),
               L(s["bio_ru"], s.get("bio_en"))))
    heading = L("Авторы и red team", "Authors & red team") if article_mode else L("Участники", "Speakers")
    return ('<section class="roster"><h2>%s</h2><div class="roster-grid">%s</div></section>'
            % (heading, "".join(cards)))


def render_chapters(chapters, vid):
    if not chapters:
        return ""
    rows = []
    for ch in chapters:
        rows.append(
            '<a class="chap" href="%s" target="_blank" rel="noopener">'
            '<span class="chap-t">%s</span><span class="chap-title">%s</span></a>'
            % (yt(vid, ch["t_seconds"]), hhmmss(ch["t_seconds"]),
               L(ch.get("title_ru") or ch.get("title_en"), ch.get("title_en"))))
    return ('<section class="chapters"><h2>%s</h2><div class="chap-list">%s</div></section>'
            % (L("Тайм-лайн глав", "Chapter timeline"), "".join(rows)))


def render_concept(pdir, c, spk_by_id, article_mode=False):
    sp = spk_by_id.get(c.get("speaker_id"))
    sp_badge = ('<span class="who who-%s">%s</span>' % (sp["role"], e(sp["name"]))) if sp else ""

    quote = ""
    if c.get("quote_en"):
        prov_lbl = ('<span class="prov" title="по авто-субтитрам, очищено">auto</span>'
                    if c.get("quote_provenance") == "auto-cleaned" else "")
        quote = '<blockquote class="q">“%s”%s</blockquote>' % (e(c["quote_en"]), prov_lbl)

    tldr = ('<p class="tldr">%s</p>' % Lc(c["tldr_ru"], c.get("tldr_en"))) if c.get("tldr_ru") else ""

    kru = c.get("key_points_ru") or []
    ken = c.get("key_points_en") or kru
    kp = ""
    if kru:
        lis = "".join('<li>%s</li>' % Lc(kru[i], ken[i] if i < len(ken) else None)
                      for i in range(len(kru)))
        kp = '<ul class="kp">%s</ul>' % lis

    is_img = c["visual"].get("type") == "image"
    if is_img:
        cap = L(c.get("analogy_ru") or c["visual"].get("title_ru"),
                c.get("analogy_en") or c.get("visual_title_en"))
    else:
        cap = L(c["visual"].get("title_ru"), c.get("visual_title_en"))
    caption = '<div class="viz-cap">%s</div>' % cap

    classes = ["concept"]
    if is_img:
        classes.append("has-img")
    if article_mode:
        classes.append("reveal")
    return (
        '<article class="%s" id="%s">'
        '<div class="concept-viz">%s%s</div>'
        '<div class="concept-body"><h3>%s %s</h3>%s'
        '<p class="lead">%s</p>%s%s</div></article>'
        % (" ".join(classes), e(c["id"]),
           render_visual(pdir, c), caption,
           e(c["term_en"]), sp_badge, tldr,
           Lc(c["explanation_ru"], c.get("explanation_en")), kp, quote))


def render_section(pdir, sec, vid, spk_by_id, article_mode=False):
    dl = ""
    if not article_mode and sec.get("t_seconds") is not None:
        dl = ('<a class="sec-dl" href="%s" target="_blank" rel="noopener">▶ %s</a>'
              % (yt(vid, sec["t_seconds"]), hhmmss(sec["t_seconds"])))
    concepts = "".join(render_concept(pdir, c, spk_by_id, article_mode)
                       for c in sec.get("concepts", []))
    evidence = render_source_docs(sec.get("source_docs")) if article_mode else ""
    sec_class = "sec reveal" if article_mode else "sec"
    return ('<section class="%s" id="%s"><div class="sec-head"><h2>%s</h2>%s</div>'
            '<p class="sec-intro">%s</p>%s%s</section>'
            % (sec_class, e(sec["id"]), L(sec["title_ru"], sec.get("title_en")), dl,
               L(sec["intro_ru"], sec.get("intro_en")), evidence, concepts))


def render_debates(debates, vid, spk_by_id, article_mode=False):
    if not debates:
        return ""
    cards = []
    for d in debates:
        pos = []
        for p in d["positions"]:
            sp = spk_by_id.get(p["speaker_id"], {})
            role = sp.get("role", "guest")
            lens = ' data-debate-role="%s"' % role if article_mode else ""
            pos.append('<div class="deb-pos deb-%s"%s><span class="deb-who">%s</span>'
                       '<p>%s</p>%s</div>'
                       % (role, lens, e(sp.get("name", p["speaker_id"])),
                          L(p["claim_ru"], p.get("claim_en")),
                          ('<blockquote class="q">“%s”</blockquote>' % e(p["quote_en"])) if p.get("quote_en") else ""))
        res = ""
        if d.get("resolution_ru"):
            res = '<div class="deb-res">%s %s</div>' % (
                L("Итог:", "Resolution:"), L(d["resolution_ru"], d.get("resolution_en")))
        dl = ""
        if not article_mode and d.get("t_seconds") is not None:
            dl = '<a class="sec-dl" href="%s" target="_blank" rel="noopener">▶ %s</a>' % (
                yt(vid, d["t_seconds"]), hhmmss(d["t_seconds"]))
        cards.append('<div class="debate"><div class="deb-head"><h3>%s</h3>%s</div>'
                     '<div class="deb-cols">%s</div>%s</div>'
                     % (L(d["topic_ru"], d.get("topic_en")), dl,
                        ("" if article_mode else '<span class="deb-vs">⟷</span>').join(pos), res))
    controls = ""
    if article_mode:
        controls = (
            '<div class="debate-lens" role="group" aria-label="Линза спора / Debate lens">'
            '<span class="lens-label">%s</span>'
            '<button type="button" data-debate-filter="all" aria-pressed="true">%s</button>'
            '<button type="button" data-debate-filter="guest" aria-pressed="false">%s</button>'
            '<button type="button" data-debate-filter="host" aria-pressed="false">%s</button>'
            '</div>' % (L("Линза спора", "Debate lens"), L("Все", "All"),
                        L("Авторы", "Authors"), L("Red team", "Red team")))
    hint = (L("Сопоставь исходные тезисы с возражениями red team.",
              "Compare author claims with the red-team objections.") if article_mode else
            L("Где спикеры спорили или вызывали друг друга.",
              "Where the speakers pushed back on each other."))
    return ('<section class="debates" id="debates"><h2>%s</h2>'
            '<p class="muted">%s</p>%s%s</section>'
            % (L("Споры и расхождения", "Debates & disagreements"),
               hint, controls, "".join(cards)))


GL_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true">'
           '<path d="M7 3h10a1 1 0 0 1 1 1v17l-6-3.6L6 21V4a1 1 0 0 1 1-1z"/></svg>')


def render_glossary(gloss, sections, article_mode=False):
    if not gloss:
        return ""
    # section_id -> (index, title_ru, title_en) для иконки-цвета и чипа секции
    sec_meta = {s["id"]: (i, s["title_ru"], s.get("title_en"))
                for i, s in enumerate(sections)}
    cards = []
    for g in sorted(gloss, key=lambda x: x["term_en"].casefold()):
        sid = g.get("section_id")
        meta = sec_meta.get(sid)
        hue = (meta[0] * 47) % 360 if meta else 210
        chip = ('<a class="gl-sec" href="#%s">%s</a>' % (e(sid), L(meta[1], meta[2]))) if meta else ""
        cards.append(
            '<div class="gl-card" data-term="%s" style="--h:%d">'
            '<span class="gl-ic">%s</span>'
            '<div class="gl-c-body"><div class="gl-term">%s</div>'
            '<div class="gl-def">%s</div>%s</div></div>'
            % (e(g["term_en"].lower()), hue, GL_ICON, e(g["term_en"]),
               Lc(g["definition_ru"], g.get("definition_en")), chip))
    heading = L("Глоссарий статьи", "Article glossary") if article_mode else L("Глоссарий эпизода", "Episode glossary")
    return ('<section class="glossary" id="glossary"><h2>%s</h2>'
            '<p class="muted">%s</p>'
            '<input id="glSearch" class="gl-search" type="search" placeholder="поиск термина…">'
            '<div class="gl-grid">%s</div></section>'
            % (heading,
               L("Цвет иконки = тема (секция), откуда термин.",
                 "Icon color = the topic (section) the term comes from."),
               "".join(cards)))


def render_qa(qa):
    if not qa:
        return ""
    items = []
    for q in qa:
        pts = "".join('<li>%s</li>' % L(p, (q.get("points_en") or [])[i] if i < len(q.get("points_en") or []) else p)
                      for i, p in enumerate(q["expected_answer_points"]))
        items.append('<details class="qa"><summary><span class="qa-diff qa-%s">%s</span> %s</summary>'
                     '<ul class="qa-points">%s</ul></details>'
                     % (e(q["difficulty"]), e(q["difficulty"]),
                        L(q["question_ru"], q.get("question_en")), pts))
    return ('<section class="qa-sec" id="qa"><h2>%s</h2><p class="muted">%s</p>%s</section>'
            % (L("Проверь себя", "Active recall"),
               L("Ответь сам, потом раскрой пункты рубрики.",
                 "Answer first, then reveal the rubric."), "".join(items)))


# ---------- full page ----------

CSS = """
:root{--bg:#fbfaf7;--fg:#1c1a17;--mut:#6b6358;--card:#fff;--line:#e7e1d6;--acc:#c8501e;--acc2:#1e6fc8;--host:#1e6fc8;--guest:#c8501e;--green:#3fae5a;--red:#e0533f;--gold:#e0a93f}
@media(prefers-color-scheme:dark){:root{--bg:#16140f;--fg:#ece7df;--mut:#9a9182;--card:#211e18;--line:#322d24;--acc:#e87242;--acc2:#5b9be8;--host:#5b9be8;--guest:#e87242;--green:#57c974;--red:#ef7461;--gold:#eec163}}
*{box-sizing:border-box}html,body{margin:0}body{background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.lang{display:none}html[lang=ru] .lang.ru{display:inline}html[lang=en] .lang.en{display:inline}
.bar{display:flex;align-items:center;gap:18px;padding:12px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:color-mix(in srgb,var(--bg) 86%,transparent);backdrop-filter:blur(8px);z-index:9}
.brandmark{font-weight:800;color:var(--acc);text-decoration:none;letter-spacing:.3px}
.navlinks{display:flex;gap:16px}.navlinks a{color:var(--fg);text-decoration:none;opacity:.78;font-size:14px}.navlinks a:hover{opacity:1}.navlinks a.active{color:var(--acc);opacity:1;font-weight:600}
.spacer{flex:1}.lang-toggle{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:5px 12px;cursor:pointer;font-size:13px}
.wrap{max-width:880px;margin:0 auto;padding:0 22px 80px}
.hero{padding:38px 0 10px}.eyebrow{color:var(--mut);font-size:13px;text-transform:uppercase;letter-spacing:.12em}
h1{font-size:33px;line-height:1.15;margin:.25em 0}.hero-meta{color:var(--mut);font-size:14px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.hero-meta a{color:var(--acc2);text-decoration:none}.summary{font-size:18px;color:var(--fg);margin:18px 0}
h2{font-size:23px;margin:34px 0 14px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.muted{color:var(--mut);font-size:14px;margin:-6px 0 14px}
.roster-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:620px){.roster-grid{grid-template-columns:1fr}}
.spk{display:flex;gap:12px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.spk-mono{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;font-weight:800;color:#fff;flex:none}
.spk-host{background:var(--host)}.spk-guest{background:var(--guest)}
.spk-name{font-weight:700}.spk-role{font-weight:400;color:var(--mut);font-size:13px}.spk-bio{color:var(--mut);font-size:14px;margin-top:3px}
.chap-list{display:flex;flex-direction:column;gap:2px}
.chap{display:flex;gap:14px;padding:8px 10px;border-radius:8px;text-decoration:none;color:var(--fg)}.chap:hover{background:var(--card)}
.chap-t{color:var(--acc2);font-variant-numeric:tabular-nums;font-size:14px;min-width:58px}.chap-title{font-size:15px}
.sec-head{display:flex;align-items:baseline;gap:12px}.sec-head h2{border:none;margin-bottom:4px}
.sec-dl{font-size:13px;color:var(--acc2);text-decoration:none;white-space:nowrap}
.sec-intro{color:var(--mut);margin:0 0 16px}
.concept{display:grid;grid-template-columns:1fr;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0}
.concept-viz{display:flex;flex-direction:column;gap:8px;align-items:center;justify-content:center}
.concept-viz>*{width:100%;max-width:480px}
.viz,.v-img{width:100%;height:auto}.viz{max-width:440px}.v-img{max-width:min(640px,100%);border-radius:12px}
.viz-cap{font-size:12.5px;color:var(--mut);text-align:center;max-width:640px}
.concept-body h3{margin:.1em 0 .3em;font-size:19px}
.tldr{margin:0 0 10px;padding:8px 12px;border-left:3px solid var(--acc);background:color-mix(in srgb,var(--acc) 7%,transparent);border-radius:0 8px 8px 0;font-weight:600;font-size:15px}
.lead{margin:0 0 10px;font-size:14.5px}
ul.kp{margin:0 0 10px;padding:0;list-style:none}
ul.kp li{position:relative;padding-left:20px;margin:5px 0;font-size:14px}
ul.kp li::before{content:"";position:absolute;left:4px;top:8px;width:6px;height:6px;border-radius:50%;background:var(--acc2)}
.concept.has-img .concept-viz{width:100%}
.who{font-size:12px;font-weight:600;padding:2px 8px;border-radius:20px;margin-left:8px;vertical-align:middle}
.who-host{background:color-mix(in srgb,var(--host) 18%,transparent);color:var(--host)}
.who-guest{background:color-mix(in srgb,var(--guest) 18%,transparent);color:var(--guest)}
.analogy{font-size:14px;color:var(--mut)}.q{border-left:3px solid var(--acc);margin:10px 0 0;padding:4px 0 4px 12px;color:var(--fg);font-style:italic}
.prov{font-style:normal;font-size:10px;color:var(--mut);border:1px solid var(--line);border-radius:4px;padding:0 4px;margin-left:6px;vertical-align:super}
.term{border-bottom:1px dashed var(--acc2);cursor:help;position:relative;white-space:nowrap}
.term::after{content:attr(data-tip);position:absolute;left:50%;bottom:calc(100% + 7px);transform:translateX(-50%);background:var(--fg);color:var(--bg);font-size:12px;font-weight:400;font-style:normal;line-height:1.35;padding:6px 9px;border-radius:7px;white-space:normal;width:max-content;max-width:230px;box-shadow:0 4px 16px rgba(0,0,0,.28);opacity:0;visibility:hidden;transition:opacity .12s;z-index:30;pointer-events:none}
.term::before{content:"";position:absolute;left:50%;bottom:calc(100% + 2px);transform:translateX(-50%);border:5px solid transparent;border-top-color:var(--fg);opacity:0;visibility:hidden;transition:opacity .12s;z-index:30}
.term:hover::after,.term:focus::after,.term:hover::before,.term:focus::before{opacity:1;visibility:visible}
.debates{}.debate{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0}
.deb-head{display:flex;align-items:baseline;gap:12px}.deb-head h3{margin:.1em 0}
.deb-cols{display:flex;gap:10px;align-items:center;margin-top:10px}@media(max-width:620px){.deb-cols{flex-direction:column}}
.deb-pos{flex:1;border-radius:10px;padding:12px;border:1px solid var(--line)}
.deb-host{border-top:3px solid var(--host)}.deb-guest{border-top:3px solid var(--guest)}
.deb-who{font-weight:700;font-size:14px}.deb-pos p{margin:6px 0 0;font-size:15px}
.deb-vs{color:var(--mut);font-size:20px}.deb-res{margin-top:12px;font-size:14px;color:var(--mut)}
.gl-search{width:100%;padding:9px 12px;border:1px solid var(--line);border-radius:9px;background:var(--card);color:var(--fg);margin-bottom:12px}
.gl-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:620px){.gl-grid{grid-template-columns:1fr}}
.gl-card{display:flex;gap:11px;background:var(--card);border:1px solid var(--line);border-left:3px solid hsl(var(--h) 60% 55%);border-radius:10px;padding:12px 13px}
.gl-ic{flex:none;width:22px;height:22px;color:hsl(var(--h) 60% 50%)}
.gl-ic svg{width:22px;height:22px;fill:currentColor}
.gl-term{font-weight:700;font-size:15px}
.gl-def{color:var(--mut);font-size:13.5px;margin:3px 0 0;line-height:1.5}
.gl-sec{display:inline-block;margin-top:8px;font-size:11px;color:hsl(var(--h) 55% 45%);text-decoration:none;background:hsl(var(--h) 60% 50% / .12);padding:2px 9px;border-radius:20px}
.gl-sec:hover{background:hsl(var(--h) 60% 50% / .22)}
.qa{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0}.qa summary{cursor:pointer;font-weight:600}
.qa-diff{font-size:11px;text-transform:uppercase;padding:1px 7px;border-radius:20px;margin-right:8px}
.qa-easy{background:#d9efe0;color:#1c7a47}.qa-medium{background:#fdeecb;color:#9a6a13}.qa-hard{background:#f7dcd2;color:#b14424}
.qa-points{margin:10px 0 2px}.qa-points li{margin:4px 0;color:var(--mut)}
/* viz internals */
.v-define{width:100%;text-align:center}.v-define-term{font-weight:800;font-size:18px;color:var(--acc)}.v-define-line{height:3px;background:var(--acc);border-radius:3px;margin-top:6px;opacity:.6}
.v-layers{display:flex;flex-direction:column;gap:5px;width:100%}.v-layer{background:color-mix(in srgb,var(--acc2) calc(12% + var(--i)*7%),var(--card));border:1px solid var(--line);border-radius:7px;padding:6px 8px;font-size:12px;text-align:center}
.cyc-ring{fill:none;stroke:var(--acc2);stroke-width:3;opacity:.5}.cyc-n{fill:var(--acc2)}.cyc-t{fill:#fff;font-size:11px;text-anchor:middle;font-weight:700}.cyc-ah{fill:var(--acc2)}
.v-steps{display:flex;flex-direction:column;gap:5px;width:100%}.v-step{display:flex;gap:8px;align-items:center;font-size:12px}.v-step-n{background:var(--acc);color:#fff;border-radius:50%;width:20px;height:20px;display:grid;place-items:center;font-size:11px;font-weight:700;flex:none}
.v-tug{display:flex;align-items:center;gap:8px;width:100%;justify-content:center;font-size:13px}.v-tug-a,.v-tug-b{flex:1;min-width:0;background:var(--card);border:1px solid var(--line);border-radius:7px;padding:6px 9px;overflow-wrap:anywhere}.v-tug-a{border-color:var(--host)}.v-tug-b{border-color:var(--guest)}.v-tug-rope{color:var(--mut);flex:none}
.v-two{display:flex;align-items:center;gap:6px;font-size:12px;justify-content:center}.v-two-old{background:color-mix(in srgb,var(--guest) 14%,var(--card));border-radius:7px;padding:5px 8px}.v-two-new{background:color-mix(in srgb,var(--host) 14%,var(--card));border-radius:7px;padding:5px 8px}.v-two-arrow{color:var(--mut)}
.v-funnel{display:flex;flex-direction:column;gap:4px;align-items:center;width:100%}.v-funnel-r{width:var(--w);background:color-mix(in srgb,var(--acc) 22%,var(--card));border:1px solid var(--line);border-radius:6px;padding:5px 8px;font-size:12.5px;text-align:center;overflow-wrap:anywhere}
.v-tl{position:relative;width:100%;display:flex;flex-direction:column;gap:13px;padding:4px 0 4px 2px}.v-tl:before{content:"";position:absolute;left:7px;top:10px;bottom:10px;width:3px;background:var(--line);border-radius:3px}.v-tl-row{display:flex;gap:10px;align-items:flex-start;position:relative}.v-tl-dot{flex:0 0 11px;width:11px;height:11px;border-radius:50%;background:var(--acc);margin-top:3px}.v-tl-l{font-size:13px;line-height:1.45;color:var(--mut);text-align:left;min-width:0;overflow-wrap:anywhere}
.m2o-l{stroke:var(--line);stroke-width:2}.m2o-s{fill:var(--acc2)}.m2o-hub{fill:var(--acc)}.m2o-t{fill:#fff;text-anchor:middle;font-size:13px;font-weight:700}
.v-split{display:flex;gap:8px;width:100%;align-items:stretch}.v-split-c{flex:1;min-width:0;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12.5px;text-align:center;overflow-wrap:anywhere}
.v-split-t{font-weight:700;font-size:13px;margin-bottom:4px}.v-split-c ul{margin:0;padding:0;list-style:none;text-align:left}.v-split-c li{position:relative;padding-left:14px;margin:4px 0}.v-split-c li:before{content:"";position:absolute;left:2px;top:8px;width:5px;height:5px;border-radius:50%;background:var(--mut)}
.v-split-l{border-top:3px solid var(--host)}.v-split-r{border-top:3px solid var(--guest)}
@media(max-width:520px){.v-split{flex-direction:column}}
/* SVG diagram layer (общие классы новых компонентов) */
.vz{display:block;margin:0 auto}
.vz text{fill:var(--mut);font-size:11px;font-weight:600;font-family:inherit}
.vz text.sm{font-size:9px}
.vz .box{fill:color-mix(in srgb,var(--acc2) 16%,var(--card));stroke:var(--acc2);stroke-width:1.5}
.vz .box.hot{fill:color-mix(in srgb,var(--acc2) 30%,var(--card));stroke:var(--acc2)}
.vz .edge{stroke:color-mix(in srgb,var(--acc2) 45%,var(--card));stroke-width:1.4}
.vz .arrowh{fill:var(--acc2)}
.vz .axis{stroke:var(--line);stroke-width:1.6}
.vz .node{fill:var(--acc2);stroke:var(--card);stroke-width:1.5}
.vz .hit{fill:var(--acc)}
.vz .line2{stroke:var(--mut);stroke-width:1.4}
.vz .pane{fill:var(--card);stroke:var(--line);stroke-width:1.6}
.vz .barfill{fill:color-mix(in srgb,var(--acc2) 55%,var(--card));animation:vzgrow .9s ease both}
.vz .barfill.good{fill:color-mix(in srgb,var(--green) 65%,var(--card))}
.vz .barfill.bad{fill:color-mix(in srgb,var(--red) 55%,var(--card))}
.vz .venn{fill:color-mix(in srgb,var(--acc2) 14%,var(--card));stroke:var(--acc2);stroke-width:1.6;mix-blend-mode:multiply}
.vz .venn.b{fill:color-mix(in srgb,var(--acc) 16%,var(--card));stroke:var(--acc)}
@media(prefers-color-scheme:dark){.vz .venn{mix-blend-mode:screen}}
.vz .orbitring{fill:none;stroke:var(--line);stroke-width:1.6;stroke-dasharray:5 4}
.vz .corehub{fill:color-mix(in srgb,var(--acc2) 22%,var(--card));stroke:var(--acc2);stroke-width:1.6}
.vz .shieldarc{fill:none;stroke:var(--acc);stroke-width:5;stroke-linecap:round;stroke-dasharray:300;stroke-dashoffset:300;animation:vzdraw 1.2s ease forwards}
.vz .gatebox{fill:color-mix(in srgb,var(--gold) 26%,var(--card));stroke:var(--gold);stroke-width:1.6}
.vz .loopring{fill:none;stroke:var(--line);stroke-width:2}
.vz .loopdash{fill:none;stroke:var(--acc);stroke-width:2.6;stroke-linecap:round;stroke-dasharray:240;stroke-dashoffset:240;animation:vzdraw 1.6s ease forwards}
.vz .arrhead{fill:none;stroke:var(--mut);stroke-width:1.6}
.vz .gaugebg{fill:none;stroke:var(--line);stroke-width:10;stroke-linecap:round}
.vz .gaugefill{fill:none;stroke:var(--acc);stroke-width:10;stroke-linecap:round;stroke-dasharray:400;stroke-dashoffset:400;animation:vzdraw 1.6s ease forwards}
.vz .needle{stroke:var(--fg);stroke-width:3;stroke-linecap:round;transform-origin:160px 130px;animation:vzswing 2.8s ease-in-out infinite alternate}
.vz .pivot{fill:var(--fg)}
@keyframes vzdraw{to{stroke-dashoffset:0}}
@keyframes vzgrow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes vzswing{from{transform:rotate(-3deg)}to{transform:rotate(3deg)}}
@media(prefers-reduced-motion:reduce){.vz *{animation:none!important}.vz .loopdash,.vz .gaugefill,.vz .shieldarc{stroke-dashoffset:0!important}.vz .barfill{transform:none!important}}

/* Article mode — treaty dossier × distributed-systems diagram */
body.article-mode{--bg:#f3efe6;--fg:#171512;--mut:#70685e;--card:#f3efe6;--line:#c9c0b1;--acc:#d3222a;--acc2:#171512;--host:#171512;--guest:#d3222a;background:#f3efe6;color:#171512;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.article-mode .bar{background:#f3efe6;border-color:#171512;backdrop-filter:none}
.article-mode .brandmark{color:#d3222a}.article-mode .navlinks a.active{color:#d3222a}
.article-mode .lang-toggle{background:transparent;border-color:#171512;border-radius:0;color:#171512}
.article-mode .wrap{max-width:none;margin:0;padding:0 0 108px}
.article-hero{min-height:calc(100svh - 55px);display:grid;grid-template-columns:minmax(320px,.78fr) minmax(520px,1.22fr);align-items:center;gap:clamp(28px,5vw,92px);position:relative;overflow:hidden;padding:clamp(56px,7vw,110px) clamp(28px,7vw,118px);border-bottom:1px solid #171512;background:#f3efe6}
.article-hero::before{content:"";position:absolute;left:clamp(16px,3vw,48px);top:0;bottom:0;width:5px;background:#d3222a}
.article-hero-copy{position:relative;z-index:2;max-width:680px}
.article-hero .eyebrow{color:#d3222a;font-size:12px;font-weight:800;letter-spacing:.18em}
.article-hero h1{font-family:Georgia,"Times New Roman",serif;font-size:clamp(44px,5.5vw,88px);font-weight:500;line-height:.96;letter-spacing:-.045em;margin:.3em 0 .28em;max-width:12ch}
.article-hero .hero-meta{padding-top:14px;border-top:1px solid #171512;color:#514b43;font-size:12px;letter-spacing:.06em;text-transform:uppercase}
.article-hero .meta-item{display:inline-flex;align-items:center;min-width:0}
.article-hero .hero-meta a{color:#171512;font-weight:800;text-underline-offset:4px}
.article-hero .summary{max-width:62ch;font-family:Georgia,"Times New Roman",serif;font-size:clamp(17px,1.5vw,22px);line-height:1.55;margin:24px 0 0}
.article-network{position:relative;z-index:1;width:100%;max-width:880px;justify-self:end}
.article-network svg{display:block;width:100%;height:auto;overflow:visible}
.article-network .dossier-rule path{fill:none;stroke:#171512;stroke-width:1;opacity:.52}
.article-network .network-line{fill:none;stroke:#171512;stroke-width:2.2;vector-effect:non-scaling-stroke;stroke-dasharray:1;stroke-dashoffset:1;animation:dossier-draw 1.05s cubic-bezier(.65,0,.35,1) forwards}
.article-network .network-line.signal{stroke:#d3222a;stroke-width:3}
.article-network .nl-2{animation-delay:.12s}.article-network .nl-3{animation-delay:.22s}.article-network .nl-4{animation-delay:.32s}.article-network .nl-5{animation-delay:.42s}.article-network .nl-6{animation-delay:.58s}
.article-network .network-node{opacity:0;transform-box:fill-box;transform-origin:center;animation:dossier-node .48s cubic-bezier(.2,.8,.2,1) forwards}
.article-network .node-a{animation-delay:.36s}.article-network .node-b{animation-delay:.5s}.article-network .node-c{animation-delay:.64s}.article-network .node-d{animation-delay:.78s}.article-network .node-e{animation-delay:.92s}
.article-network .network-node>circle,.article-network .network-node>rect,.article-network .network-node>path{fill:#f3efe6;stroke:#171512;stroke-width:2;vector-effect:non-scaling-stroke}
.article-network .network-node .node-core{fill:#d3222a;stroke:none}
.article-network text{fill:#171512;font:700 12px/1 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:.12em}
.article-network .dossier-seal{opacity:0;animation:dossier-stamp .46s cubic-bezier(.2,.9,.25,1.25) 1.08s forwards}
.article-network .dossier-seal circle,.article-network .dossier-seal path{fill:none;stroke:#d3222a;stroke-width:3}
.article-network .dossier-seal text{fill:#d3222a}
.article-network .dossier-index text{font-size:10px;letter-spacing:.18em}
@keyframes dossier-draw{to{stroke-dashoffset:0}}
@keyframes dossier-node{from{opacity:0;scale:.72}to{opacity:1;scale:1}}
@keyframes dossier-stamp{from{opacity:0;scale:1.35;rotate:-8deg}to{opacity:.86;scale:1;rotate:-8deg}}
@keyframes article-enter{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
.article-hero-copy>*{opacity:0;animation:article-enter .55s ease forwards}.article-hero-copy .eyebrow{animation-delay:.08s}.article-hero-copy h1{animation-delay:.18s}.article-hero-copy .hero-meta{animation-delay:.3s}.article-hero-copy .summary{animation-delay:.4s}
.article-mode .roster,.article-mode .chapters,.article-mode .sec,.article-mode .debates,.article-mode .glossary,.article-mode .qa-sec{width:min(1120px,calc(100% - 64px));margin-left:auto;margin-right:auto}
.article-mode h2{font-family:Georgia,"Times New Roman",serif;font-size:clamp(30px,4vw,54px);font-weight:500;line-height:1.05;letter-spacing:-.035em;border-color:#171512}
.article-mode .roster{padding-top:38px}.article-mode .roster-grid{gap:0;border-top:1px solid #171512}
.article-mode .spk{background:transparent;border:0;border-bottom:1px solid #c9c0b1;border-radius:0;padding:18px 4px}.article-mode .spk-mono{border-radius:0;background:#171512}.article-mode .spk-guest{background:#d3222a}
.article-mode .sec{padding-top:70px}.article-mode .sec-head{align-items:flex-end}.article-mode .sec-head h2{flex:1;margin:0;padding:0 0 18px;border-bottom:1px solid #171512}
.article-mode .sec-intro{font-family:Georgia,"Times New Roman",serif;color:#514b43;font-size:19px;max-width:760px;margin:20px 0 8px}
.evidence-links{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:16px 0 10px}
.evidence-label{font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#d3222a;margin-right:5px}
.evidence-link{display:inline-block;color:#171512;border:1px solid #8f877b;padding:4px 8px;text-decoration:none;font-size:11px;line-height:1.25}.evidence-link:hover,.evidence-link:focus-visible{border-color:#d3222a;color:#d3222a;outline:none}
.article-mode .concept,.article-mode .concept.has-img{grid-template-columns:minmax(190px,280px) minmax(0,1fr);gap:clamp(30px,5vw,72px);background:transparent;border:0;border-top:1px solid #c9c0b1;border-radius:0;padding:42px 0;margin:0}
.article-mode .concept:last-child{border-bottom:1px solid #c9c0b1}
.article-mode .concept-viz{align-items:flex-start;justify-content:flex-start}.article-mode .viz,.article-mode .v-img,.article-mode .concept.has-img .v-img{max-width:260px;border-radius:0;filter:none}
.article-mode .viz-cap{text-align:left;font-size:11px;line-height:1.35;text-transform:uppercase;letter-spacing:.05em;color:#70685e}
.article-mode .concept-body h3{font-family:Georgia,"Times New Roman",serif;font-size:clamp(25px,3vw,38px);font-weight:500;line-height:1.08;margin:0 0 14px;letter-spacing:-.025em}
.article-mode .who{border:1px solid currentColor;border-radius:0;background:transparent;padding:2px 6px}
.article-mode .tldr{font-family:Georgia,"Times New Roman",serif;font-size:18px;line-height:1.45;background:transparent;border-radius:0;border-left:4px solid #d3222a;padding:0 0 0 16px;margin:0 0 18px}
.article-mode .lead{font-size:16px;line-height:1.7}.article-mode ul.kp li{font-size:15px;line-height:1.55;padding-left:18px}.article-mode ul.kp li::before{border-radius:0;background:#d3222a;width:7px;height:2px;top:11px;left:0}
.article-mode .q{border-color:#171512;font-family:Georgia,"Times New Roman",serif;font-size:16px}
.article-mode .debates{padding-top:72px}.article-mode .debate-lens{display:flex;align-items:center;gap:0;flex-wrap:wrap;margin:18px 0 30px}.lens-label{margin-right:14px;font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#70685e}
.article-mode .debate-lens button{appearance:none;border:1px solid #171512;border-right:0;background:transparent;color:#171512;padding:8px 13px;font:700 12px/1 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;cursor:pointer}.article-mode .debate-lens button:last-child{border-right:1px solid #171512}.article-mode .debate-lens button[aria-pressed="true"]{background:#d3222a;color:#fff;border-color:#d3222a}.article-mode .debate-lens button:focus-visible{outline:3px solid #d3222a;outline-offset:3px}
.article-mode .debate{background:transparent;border:0;border-top:1px solid #171512;border-radius:0;padding:26px 0;margin:0}.article-mode .deb-cols{align-items:stretch;gap:0}.article-mode .deb-pos{border:0;border-left:4px solid #171512;border-radius:0;padding:5px 22px}.article-mode .deb-guest{border-color:#d3222a}.article-mode .deb-res{border-top:1px solid #c9c0b1;padding-top:14px}
.article-mode .gl-grid{gap:0;border-top:1px solid #171512}.article-mode .gl-card{background:transparent;border:0;border-bottom:1px solid #c9c0b1;border-left:3px solid #d3222a;border-radius:0;padding:16px}.article-mode .gl-ic{color:#d3222a!important}.article-mode .gl-sec{border-radius:0;background:transparent;border:1px solid #c9c0b1;color:#171512}
.article-mode .gl-search{background:transparent;border-color:#171512;border-radius:0}.article-mode .qa{background:transparent;border:0;border-top:1px solid #c9c0b1;border-radius:0;padding:15px 0;margin:0}.article-mode .qa:last-child{border-bottom:1px solid #c9c0b1}
.article-mode.motion-ready .reveal{opacity:0;transform:translateY(30px);transition:opacity .55s ease,transform .7s cubic-bezier(.2,.75,.2,1);transition-delay:var(--reveal-delay,0ms)}
.article-mode.motion-ready .reveal.is-visible{opacity:1;transform:none}
@media(max-width:840px){.article-hero{min-height:auto;display:flex;flex-direction:column;align-items:stretch;padding:58px 28px 36px 42px}.article-hero-copy{display:contents}.article-hero>* ,.article-hero-copy>*{min-width:0;max-width:100%}.article-hero .eyebrow{order:1;position:relative;z-index:2}.article-hero h1{order:2;position:relative;z-index:2;font-size:clamp(44px,12vw,70px);width:100%;overflow-wrap:anywhere}.article-hero .hero-meta{order:3;position:relative;z-index:2;width:100%;white-space:normal}.article-network{order:4;width:100%;min-width:0;max-width:680px;align-self:center;margin:10px 0 18px;overflow:hidden}.article-network svg{max-width:100%}.article-hero .summary{order:5;position:relative;z-index:2;width:100%;margin-top:0}.article-mode .roster,.article-mode .chapters,.article-mode .sec,.article-mode .debates,.article-mode .glossary,.article-mode .qa-sec{width:min(100% - 36px,720px)}.article-mode .concept,.article-mode .concept.has-img{grid-template-columns:1fr;padding:30px 0}.article-mode .concept-viz{max-width:300px}.article-mode .deb-cols{flex-direction:column;gap:20px}.article-mode .deb-pos{width:100%}}
@media(max-width:560px){.article-mode .bar{gap:10px;padding:10px 14px;flex-wrap:wrap}.article-mode .navlinks{order:3;width:100%;gap:10px;overflow-x:auto}.article-mode .navlinks a{white-space:nowrap}.article-hero{padding:48px 20px 30px 32px}.article-hero::before{left:12px;width:4px}.article-hero h1{font-size:clamp(40px,10.8vw,58px);max-width:100%;overflow-wrap:break-word}.article-hero .hero-meta{max-width:100%;overflow-wrap:anywhere}.article-hero .summary{font-size:17px}.article-network{width:100%;margin-left:0}.article-mode .sec{padding-top:52px}.article-mode h2{font-size:34px}.article-mode .debate-lens{align-items:stretch}.article-mode .lens-label{width:100%;margin:0 0 8px}.article-mode .debate-lens button{flex:1;padding:9px 7px}.article-mode .gl-grid{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.article-hero-copy>*,.article-network .network-line,.article-network .network-node,.article-network .dossier-seal{animation:none!important;opacity:1!important;transform:none!important;scale:1!important;rotate:0deg!important;stroke-dashoffset:0!important}.article-mode.motion-ready .reveal{opacity:1;transform:none;transition:none}}
"""

JS = """
(function(){
 var KEY='deepdive-lang';
 function set(l){document.documentElement.lang=l;localStorage.setItem(KEY,l);var b=document.getElementById('langToggle');if(b)b.textContent=(l==='ru'?'EN':'RU');}
 set(localStorage.getItem(KEY)||'ru');
 var b=document.getElementById('langToggle');if(b)b.onclick=function(){set(document.documentElement.lang==='ru'?'en':'ru');};
 var s=document.getElementById('glSearch');if(s)s.oninput=function(){var q=this.value.toLowerCase();document.querySelectorAll('.gl-card').forEach(function(r){r.style.display=r.getAttribute('data-term').indexOf(q)>=0?'':'none';});};
 var body=document.body;
 if(body.classList.contains('article-mode')){
  body.classList.add('motion-ready');
  var reduced=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var reveals=[].slice.call(document.querySelectorAll('.reveal'));
  reveals.forEach(function(el,i){el.style.setProperty('--reveal-delay',Math.min(i%4,3)*55+'ms');});
  if(reduced||!('IntersectionObserver' in window)){
   reveals.forEach(function(el){el.classList.add('is-visible');});
  }else{
   var io=new IntersectionObserver(function(entries){entries.forEach(function(entry){if(entry.isIntersecting){entry.target.classList.add('is-visible');io.unobserve(entry.target);}});},{rootMargin:'0px 0px -8% 0px',threshold:.08});
   reveals.forEach(function(el){io.observe(el);});
  }
  document.querySelectorAll('.debate-lens').forEach(function(group){
   var section=group.closest('.debates');
   var buttons=[].slice.call(group.querySelectorAll('button[data-debate-filter]'));
   buttons.forEach(function(btn){btn.addEventListener('click',function(){
    var filter=btn.getAttribute('data-debate-filter');
    buttons.forEach(function(x){x.setAttribute('aria-pressed',x===btn?'true':'false');});
    section.querySelectorAll('.deb-pos[data-debate-role]').forEach(function(pos){
     pos.hidden=filter!=='all'&&pos.getAttribute('data-debate-role')!==filter;
    });
   });});
  });
 }
})();
"""


def build(pdir):
    p = load(pdir)
    slug = os.path.basename(os.path.normpath(pdir))
    ep = p["episode"]
    vid = ep["youtube_id"]
    article_mode = vid == ""
    spk_by_id = {s["id"]: s for s in p.get("speakers", [])}

    if article_mode:
        meta_bits = [L("Статья", "Article") + " · " + e(ep["show"])]
    else:
        meta_bits = [L("Подкаст", "Podcast") + " · " + e(ep["show"])]
    if ep.get("duration_hhmmss"):
        meta_bits.append(e(ep["duration_hhmmss"]))
    if article_mode:
        if ep.get("url"):
            meta_bits.append('<a href="%s" target="_blank" rel="noopener">%s</a>'
                             % (e(ep["url"]), L("Оригинал ↗", "Original ↗")))
    else:
        meta_bits.append('<a href="%s" target="_blank" rel="noopener">YouTube ↗</a>' % yt(vid, None))
    n_c = sum(len(s.get("concepts", [])) for s in p.get("sections", []))
    meta_bits.append(L("%d концептов" % n_c, "%d concepts" % n_c))
    meta_html = ("".join('<span class="meta-item">%s</span>' % bit for bit in meta_bits)
                 if article_mode else " · ".join(meta_bits))

    body = []
    if article_mode:
        body.append('<section class="hero article-hero"><div class="article-hero-copy">'
                    '<div class="eyebrow">%s</div><h1>%s</h1>'
                    '<div class="hero-meta">%s</div><p class="summary">%s</p></div>%s</section>'
                    % (L("Разбор статьи", "Article deep-dive"),
                       L(ep["title_ru"], ep["title_en_disp"]),
                       meta_html,
                       Lc(ep["summary_ru"], ep.get("summary_en")),
                       article_network_visual()))
    else:
        body.append('<div class="hero"><div class="eyebrow">%s</div><h1>%s</h1>'
                    '<div class="hero-meta">%s</div><p class="summary">%s</p></div>'
                    % (L("Разбор эпизода", "Episode deep-dive"),
                       L(ep["title_ru"], ep["title_en_disp"]),
                       meta_html,
                       L(ep["summary_ru"], ep.get("summary_en"))))
    body.append(render_roster(p.get("speakers", []), article_mode))
    if not article_mode:
        body.append(render_chapters(p.get("chapters", []), vid))
    for sec in p.get("sections", []):
        body.append(render_section(pdir, sec, vid, spk_by_id, article_mode))
    body.append(render_debates(p.get("debates", []), vid, spk_by_id, article_mode))
    body.append(render_glossary(p.get("glossary", []), p.get("sections", []), article_mode))
    body.append(render_qa(p.get("qa_seeds", [])))

    body_open = '<body class="article-mode">' if article_mode else '<body>'
    doc = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           '<title>%s — %s</title><style>%s</style></head>%s%s'
           '<main class="wrap">%s</main><script>%s</script></body></html>'
           % (e(ep["title_en_disp"]), e(ep["show"]), CSS, body_open, nav_html(ep["show"]),
              "".join(body), JS))
    out = os.path.join(pdir, slug + ".html")
    open(out, "w", encoding="utf-8").write(doc)
    print("✓ %s (%d секций, %d концептов, %d споров, %d терминов, %d Q&A)"
          % (out, len(p.get("sections", [])), n_c, len(p.get("debates", [])),
             len(p.get("glossary", [])), len(p.get("qa_seeds", []))))


def main():
    root = find_root()
    if len(sys.argv) > 1:
        dirs = [os.path.abspath(sys.argv[1])]
    else:
        base = os.path.join(root, "podcasts")
        dirs = [os.path.join(base, d) for d in sorted(os.listdir(base))
                if os.path.isfile(os.path.join(base, d, "podcast.json"))] if os.path.isdir(base) else []
    if not dirs:
        sys.exit("Нет podcasts/*/podcast.json для сборки.")
    for d in dirs:
        if os.path.isfile(os.path.join(d, "podcast.json")):
            build(d)


if __name__ == "__main__":
    main()
