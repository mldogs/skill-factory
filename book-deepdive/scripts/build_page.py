#!/usr/bin/env python3
"""build_page.py — render a self-contained interactive bilingual explainer page
for ANY book deep-dive from <book_dir>/book.json (+ optional <book_dir>/i18n).

Part of the `book-deepdive` skill. Generic: every concept declares its visual in
book.json via `visual.component` (one of the inline-SVG/CSS components below) and
optional `visual.params`; `visual.type == "image"` uses `visual.cache_filename`
if that file exists, otherwise it falls back to the declared component. Each
section lists its deep-dive markdown in `source_docs`. Output is
<book_dir>/<slug>.html (slug = book dir name). Bilingual via the project's
dual-span convention; shared top nav with the Книги/Books tab active. Q&A uses
native <details>; the glossary has a live filter; the RU/EN toggle and the
network/budget SVGs are wired in a small inline script.

Stdlib only. Usage:
    python3 build_page.py                 # build every books/*/ under the project root
    python3 build_page.py books/<slug>    # build one book dir
"""
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def find_root(start=None):
    """Walk up to the nearest dir containing '.env' or a 'books'/'week_*' dir."""
    import glob as _glob
    cur = os.path.abspath(start or os.getcwd())
    seen = set()
    while cur not in seen:
        seen.add(cur)
        if (os.path.isfile(os.path.join(cur, ".env"))
                or os.path.isdir(os.path.join(cur, "books"))
                or any(os.path.isdir(p) for p in _glob.glob(os.path.join(cur, "week_*")))):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(start or os.getcwd())


# --------------------------------------------------------------------------- #
# Data loading / merge — read <book_dir>/book.json (+ optional <book_dir>/i18n)
# --------------------------------------------------------------------------- #
def load(book_dir):
    book = json.load(open(os.path.join(book_dir, "book.json"), encoding="utf-8"))
    i18n = os.path.join(book_dir, "i18n")
    gpath = os.path.join(i18n, "_global.json")
    glob = json.load(open(gpath, encoding="utf-8")) if os.path.isfile(gpath) else {}
    book["summary_en"] = glob.get("summary_en", "") or book.get("summary_ru", "")
    gdef = {g["term_en"]: g.get("definition_en", "") for g in glob.get("glossary", [])}
    for g in book.get("glossary", []):
        g["definition_en"] = gdef.get(g["term_en"], "") or g.get("definition_ru", "")
    qmap = {q["id"]: q for q in glob.get("qa", [])}
    for q in book.get("qa_seeds", []):
        tr = qmap.get(q["id"], {})
        q["question_en"] = tr.get("question_en", "") or q.get("question_ru", "")
        q["expected_answer_points_en"] = tr.get("expected_answer_points_en", []) or q.get("expected_answer_points", [])
    for s in book.get("sections", []):
        spath = os.path.join(i18n, s["id"] + ".json")
        tr = json.load(open(spath, encoding="utf-8")) if os.path.isfile(spath) else {}
        s["intro_en"] = tr.get("intro_en", "") or s.get("intro_ru", "")
        cmap = {c["id"]: c for c in tr.get("concepts", [])}
        for c in s.get("concepts", []):
            ct = cmap.get(c["id"], {})
            c["explanation_en"] = ct.get("explanation_en", "") or c.get("explanation_ru", "")
            c["analogy_en"] = ct.get("analogy_en") if "analogy_en" in ct else c.get("analogy_ru")
            vis = c.setdefault("visual", {})
            vis["title_en"] = ct.get("visual_title_en", "") or vis.get("title_ru", "")
    return book


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def bl(ru, en, tag="span", cls=""):
    """Bilingual dual-span block."""
    c = (" " + cls) if cls else ""
    return ('<{t} class="lang ru{c}">{ru}</{t}><{t} class="lang en{c}">{en}</{t}>'
            .format(t=tag, c=c, ru=ru, en=en))


_HL = None


def build_highlighter(terms):
    global _HL
    pool = sorted({t for t in terms if len(t) >= 4}, key=len, reverse=True)
    if not pool:
        _HL = None
        return
    _HL = re.compile("(" + "|".join(re.escape(esc(t)) for t in pool) + ")")


def hl(text):
    """Escape then wrap known terms in <span class='t'>. Safe: single pass over
    the already-escaped string with a combined alternation (no nested matches)."""
    e = esc(text)
    if _HL is None:
        return e
    return _HL.sub(r'<span class="t">\1</span>', e)


# --------------------------------------------------------------------------- #
# Visual generators — each returns inline SVG/HTML for a concept card.
# Diagram labels stay short/neutral (English terms are language-neutral);
# the bilingual caption carries the meaning.
# --------------------------------------------------------------------------- #
def _svg(body, vb="0 0 320 168", cls=""):
    return ('<svg class="dgm {cls}" viewBox="{vb}" preserveAspectRatio="xMidYMid meet" '
            'role="img" aria-hidden="true">{body}</svg>').format(cls=cls, vb=vb, body=body)


def _txt(x, y, s, cls="lbl", anchor="middle"):
    return '<text x="{x}" y="{y}" text-anchor="{a}" class="{c}">{s}</text>'.format(
        x=x, y=y, a=anchor, c=cls, s=esc(s))


def v_image(src, alt):
    return ('<figure class="imgfig"><img src="{src}" alt="{alt}" loading="lazy"></figure>'
            .format(src=esc(src), alt=esc(alt)))


def v_pipeline_vs_loop(p):
    # left: straight pipeline; right: tangled loop
    steps = "".join(
        '<rect x="{x}" y="58" width="34" height="22" rx="5" class="box"/>'.format(x=14 + i * 40)
        + ('<path d="M{a} 69 h7" class="arr"/>'.format(a=48 + i * 40) if i < 2 else '')
        for i in range(3))
    # labels sit below the loop (circle bottom = 103), not across it
    left = '<g>{s}</g>'.format(s=steps) + _txt(64, 126, p.get("left", "rational / waterfall"))
    loop = ('<g transform="translate(232,69)">'
            '<circle r="34" class="loopring"/>'
            '<path d="M0,-34 A34,34 0 1 1 -3,-33.8" class="loopdash"/>'
            '<path d="M-15,-40 l10,6 l-10,6" class="arrhead"/>'
            '</g>') + _txt(232, 126, p.get("right", "iterate / build-to-learn"))
    return _svg(left + loop)


def v_tree(p):
    variant = p.get("variant", "descend")
    nodes = [(160, 24)]
    edges = []
    # 3-level binary-ish tree
    lvl1 = [(96, 70), (224, 70)]
    lvl2 = [(56, 122), (124, 122), (196, 122), (264, 122)]
    for n in lvl1:
        edges.append((160, 24, n[0], n[1]))
    pair = [(56, 124), (124, 196), (196, 264)]
    edges += [(96, 70, 56, 122), (96, 70, 124, 122), (224, 70, 196, 122), (224, 70, 264, 122)]
    alln = nodes + lvl1 + lvl2
    body = ""
    for i, (x1, y1, x2, y2) in enumerate(edges):
        cls = "edge"
        if variant == "descend" and (x1, y1, x2, y2) in [(160, 24, 96, 70), (96, 70, 124, 122)]:
            cls = "edge hot"
        if variant == "backtrack" and (x1, y1, x2, y2) == (224, 70, 264, 122):
            cls = "edge dead"
        body += '<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" class="{cl}"/>'.format(a=x1, b=y1, c=x2, d=y2, cl=cls)
    if variant == "crack":
        body += '<path d="M160,12 l-6,12 l8,8 l-6,10" class="crack"/>'
    grow = " grow" if variant == "grow" else ""
    for i, (x, y) in enumerate(alln):
        cls = "node"
        if variant == "descend" and (x, y) in [(160, 24), (96, 70), (124, 122)]:
            cls = "node hot"
        if variant == "backtrack" and (x, y) == (264, 122):
            cls = "node dead"
        body += '<circle cx="{x}" cy="{y}" r="9" class="{cl}{g}" style="animation-delay:{d}ms"/>'.format(
            x=x, y=y, cl=cls, g=grow, d=i * 80)
    if variant == "backtrack":
        body += '<path d="M264,122 q-30,18 -70,2" class="arr back"/>'
    cap = {"explode": "combinatorial blow-up", "descend": "descend the tree",
           "grow": "the tree grows as you go", "backtrack": "dead end → back up",
           "crack": "a wrong root cracks everything", "maze": "search a design space"}.get(variant, "")
    body += _txt(160, 156, p.get("cap", cap))
    return _svg(body)


def v_spiral(p):
    import math
    double = p.get("variant") == "double"

    def spath(rot=0.0):
        # true Archimedean spiral, bounded to r<=52 so it never hits the caption
        pts = []
        n = 120
        for k in range(n + 1):
            t = k / n
            r = 4 + 48 * t
            a = rot + t * 3 * 2 * math.pi
            pts.append("{0},{1}".format(round(160 + r * math.cos(a), 1),
                                        round(80 + r * math.sin(a), 1)))
        return "M" + " L".join(pts)

    body = '<path d="{d}" class="spiral"/>'.format(d=spath())
    if double:
        body += '<path d="{d}" class="spiral two"/>'.format(d=spath(math.pi))
        body += _txt(160, 158, p.get("cap", "problem ↔ solution co-evolve"))
    else:
        for i, r in enumerate([14, 28, 42, 56]):
            body += '<circle cx="160" cy="80" r="{r}" class="ring" style="animation-delay:{d}ms"/>'.format(r=r, d=i * 160)
        body += _txt(160, 158, p.get("cap", "spiral: each loop reduces risk"))
    return _svg(body, vb="0 0 320 170")


def v_funnel(p):
    body = ('<path d="M40,30 L280,30 L196,96 L196,150 L124,150 L124,96 Z" class="funnel"/>')
    for i in range(6):
        body += '<circle cx="{x}" cy="20" r="5" class="drop" style="animation-delay:{d}ms"/>'.format(
            x=70 + i * 36, d=i * 220)
    body += '<circle cx="160" cy="138" r="5" class="drop keep"/>'
    body += _txt(160, 166, p.get("cap", "many wanted → few survive"))
    return _svg(body, vb="0 0 320 176")


def v_tug(p):
    body = (
        '<line x1="40" y1="84" x2="280" y2="84" class="rope"/>'
        '<circle cx="160" cy="84" r="6" class="knot"/>'
        '<rect x="22" y="64" width="34" height="40" rx="6" class="box left"/>'
        '<rect x="264" y="64" width="34" height="40" rx="6" class="box right"/>'
        + (_txt(14, 122, p.get("left", "contract"), anchor="start")
           + _txt(306, 122, p.get("right", "iterate"), anchor="end")
           if ("left" in p or "right" in p) else
           _txt(39, 122, p.get("left", "contract")) + _txt(281, 122, p.get("right", "iterate")))
        + _txt(160, 152, p.get("cap", "fixed scope vs. learning")))
    return _svg(body)


def v_budget(p):
    # interactive: a budgeted resource split across parts; slider reallocates
    return ('<div class="budget" data-viz="budget">'
            '<div class="bbar">'
            '<span class="seg s1" style="width:34%">CPU</span>'
            '<span class="seg s2" style="width:26%">RAM</span>'
            '<span class="seg s3" style="width:22%">I/O</span>'
            '<span class="seg s4" style="width:18%">spare</span>'
            '</div>'
            '<p class="brow"><b>'
            + bl("дефицитный ресурс — 100%", "scarce resource — 100%")
            + '</b></p>'
            '<input type="range" min="6" max="60" value="34" class="bslider" aria-label="reallocate">'
            '</div>')


def v_two_targets(p):
    def target(cx, foggy, label):
        rings = "".join('<circle cx="{cx}" cy="80" r="{r}" class="ring2{f}"/>'.format(
            cx=cx, r=r, f=(" fog" if foggy else "")) for r in (34, 24, 14))
        dot = '' if foggy else '<circle cx="{cx}" cy="74" r="5" class="hit"/>'.format(cx=cx)
        return '<g>{r}{d}{l}</g>'.format(r=rings, d=dot, l=_txt(cx, 132, label))
    return _svg(target(92, True, p.get("left", "vague")) + target(228, False, p.get("right", "explicit guess"))
                + _txt(160, 156, p.get("cap", "better wrong than vague")), vb="0 0 320 164")


def v_timeline(p):
    variant = p.get("variant", "change")
    body = '<line x1="20" y1="80" x2="300" y2="80" class="axis"/>'
    if variant == "brookslaw":
        body += '<line x1="20" y1="80" x2="190" y2="80" class="plan"/>'
        body += '<line x1="190" y1="80" x2="290" y2="80" class="slip"/>'
        for x in (70, 120, 170):
            body += '<circle cx="{x}" cy="80" r="4" class="person"/>'.format(x=x)
        body += '<path d="M190,72 l0,-16" class="arr"/>' + _txt(240, 60, "+people → later")
        body += _txt(160, 130, "Brooks's Law: adding people slips the date")
    else:
        body += '<rect x="20" y="70" width="120" height="20" rx="4" class="freeze"/>'
        body += '<rect x="150" y="70" width="150" height="20" rx="4" class="flex"/>'
        for i in range(5):
            body += '<path d="M{x},66 v-10" class="arr small"/>'.format(x=170 + i * 28)
        body += _txt(80, 112, "freeze") + _txt(225, 112, "expect change")
        body += _txt(160, 138, "budget for requirements churn")
    return _svg(body, vb="0 0 320 148")


def v_gauge(p):
    body = ('<path d="M40,130 A120,120 0 0 1 280,130" class="gaugebg"/>'
            '<path d="M40,130 A120,120 0 0 1 160,40" class="gaugefill"/>'
            '<line x1="160" y1="130" x2="96" y2="66" class="needle"/>'
            '<circle cx="160" cy="130" r="7" class="pivot"/>')
    # end labels pinned to the edges; caption a line lower so texts can't collide
    body += (_txt(16, 150, p.get("left", "parsimony"), anchor="start")
             + _txt(304, 150, p.get("right", "bloat"), anchor="end")
             + _txt(160, 168, p.get("cap", "elegance = economy of means")))
    return _svg(body, vb="0 0 320 176")


def v_principles(p):
    parent = p.get("parent", "consistency")
    kl = (list(p.get("kids") or ["orthogonality", "propriety", "generality"]) + ["", "", ""])[:3]
    pw = max(84, 7 * len(parent) + 18) if "parent" in p else 84  # fit long custom titles
    body = ('<rect x="{x}" y="18" width="{w}" height="30" rx="7" class="box hot"/>'.format(
        x=160 - pw // 2, w=pw)
        + _txt(160, 38, parent))
    for label, x in zip(kl, (60, 160, 260)):
        body += '<line x1="160" y1="48" x2="{x}" y2="92" class="edge"/>'.format(x=x)
        body += '<rect x="{lx}" y="92" width="92" height="28" rx="7" class="box"/>'.format(lx=x - 46)
        body += _txt(x, 110, label)
    body += _txt(160, 150, p.get("cap", "consistency breeds three principles"))
    return _svg(body, vb="0 0 320 158")


def v_grid_style(p):
    def grid(ox, jitter):
        cells = ""
        for r in range(3):
            for c in range(3):
                dx = ((r + c) % 2) * jitter
                cells += '<rect x="{x}" y="{y}" width="20" height="20" rx="3" class="cell"/>'.format(
                    x=ox + c * 26 + dx, y=24 + r * 26 + (dx if c == 1 else 0))
        return cells
    body = grid(28, 0) + grid(196, 7)
    body += _txt(66, 130, "consistent") + _txt(236, 130, "ad-hoc")
    body += _txt(160, 152, "style = thousands of micro-decisions")
    return _svg(body, vb="0 0 320 160")


def v_arch(p):
    body = ('<path d="M70,140 L70,86 A90,46 0 0 1 250,86 L250,140" class="arch"/>'
            '<path d="M148,52 L172,52 L182,78 L138,78 Z" class="keystone"/>'
            '<rect x="250" y="60" width="46" height="58" rx="4" class="sheet"/>')
    for i in range(4):
        body += '<line x1="256" y1="{y}" x2="290" y2="{y}" class="line2"/>'.format(y=72 + i * 11)
    body += _txt(160, 158, "the keystone: write the style down")
    return _svg(body, vb="0 0 320 166")


def v_view_rays(p):
    body = '<rect x="120" y="64" width="80" height="56" rx="4" class="house"/>'
    for ang in range(0, 360, 30):
        import math
        a = math.radians(ang)
        x2 = 160 + 150 * math.cos(a)
        y2 = 92 + 90 * math.sin(a)
        body += '<line x1="160" y1="92" x2="{x}" y2="{y}" class="ray" style="animation-delay:{d}ms"/>'.format(
            x=round(x2, 1), y=round(y2, 1), d=ang * 4)
    body += '<circle cx="160" cy="92" r="6" class="node hot"/>'
    body += _txt(160, 158, "View/360: the view is the commodity")
    return _svg(body, vb="0 0 320 166")


def v_line_chart(p):
    up = p.get("variant") == "up"
    if up:
        path = "M30,130 C90,126 150,110 210,80 S290,30 300,26"
        cap = "cost of a defect rises over time"
    else:
        path = "M30,40 C90,52 150,86 210,108 S290,128 300,132"
        cap = "integrity falls as minds are added"
    body = ('<line x1="30" y1="20" x2="30" y2="134" class="axis"/>'
            '<line x1="30" y1="134" x2="304" y2="134" class="axis"/>'
            '<path d="{p}" class="curve"/>'.format(p=path)
            + _txt(167, 158, p.get("cap", cap)))
    return _svg(body, vb="0 0 320 166")


def v_floor_ceiling(p):
    body = ('<rect x="40" y="44" width="240" height="74" rx="6" class="band"/>'
            '<line x1="40" y1="100" x2="280" y2="100" class="floor"/>'
            '<line x1="40" y1="58" x2="280" y2="58" class="ceil"/>'
            '<path d="M150,100 l0,-10 M148,92 l2,-4 2,4" class="arr up"/>'
            '<path d="M210,58 l0,-10 M208,50 l2,-4 2,4" class="arr up hot"/>'
            + _txt(150, 116, "process") + _txt(212, 74, "talent")
            + _txt(160, 150, "process lifts the floor; talent lifts the ceiling"))
    return _svg(body, vb="0 0 320 158")


def v_ladder(p):
    body = ""
    for x, label in [(96, p.get("left", "management")), (224, p.get("right", "technical"))]:
        body += '<line x1="{a}" y1="20" x2="{a}" y2="132" class="rail"/>'.format(a=x - 16)
        body += '<line x1="{a}" y1="20" x2="{a}" y2="132" class="rail"/>'.format(a=x + 16)
        for r in range(5):
            body += '<line x1="{l}" y1="{y}" x2="{r}" y2="{y}" class="rung" style="animation-delay:{d}ms"/>'.format(
                l=x - 16, r=x + 16, y=36 + r * 22, d=r * 90)
        body += _txt(x, 150, label)
    body += '<path d="M112,76 h96" class="bridge2"/>'
    body += _txt(160, 164, p.get("cap", "dual ladder keeps designers designing"))
    return _svg(body, vb="0 0 320 172")


def v_cycle(p):
    import math
    body = ('<circle cx="160" cy="84" r="50" class="loopring"/>'
            '<path d="M160,34 A50,50 0 1 1 116,108" class="loopdash"/>'
            '<path d="M120,98 l-6,12 l13,-2" class="arrhead"/>')
    # default: 4 unlabeled nodes (back-compat). Pass params.nodes to label them.
    labels = p.get("nodes")
    ring = list(labels) if labels else ["", "", "", ""]
    n = max(len(ring), 1)
    for i, lab in enumerate(ring):
        a = math.radians(-90 + i * 360 / n)
        x = 160 + 50 * math.cos(a)
        y = 84 + 50 * math.sin(a)
        body += '<circle cx="{x}" cy="{y}" r="7" class="node"/>'.format(x=round(x, 1), y=round(y, 1))
        if lab:
            # push labels clear of the ring; anchor away from it so long
            # labels grow outward instead of crossing the circle
            c_, s_ = math.cos(a), math.sin(a)
            lx = 160 + 66 * c_
            ly = 84 + 66 * s_ + 4
            anchor = "start" if c_ > 0.35 else ("end" if c_ < -0.35 else "middle")
            body += _txt(round(lx, 1), round(ly, 1), lab, cls="lbl sm", anchor=anchor)
    if labels:
        body += _txt(160, 166, p.get("cap", "success can hide the next failure"))
        return _svg(body, vb="0 0 320 174")
    body += _txt(160, 158, p.get("cap", "success can hide the next failure"))
    return _svg(body, vb="0 0 320 168")


def v_split(p):
    lg = p.get("left_good", True)
    rg = p.get("right_good", False)
    ll = p.get("left", "with")
    rl = p.get("right", "without")

    def mark(good):
        return ('<path d="M-8,0 l6,7 l11,-14" class="ok"/>' if good
                else '<path d="M-8,-8 l16,16 M8,-8 l-16,16" class="bad"/>')
    body = ('<rect x="20" y="26" width="124" height="92" rx="8" class="pane {0}"/>'.format("good" if lg else "bad")
            + '<rect x="176" y="26" width="124" height="92" rx="8" class="pane {0}"/>'.format("good" if rg else "bad")
            + '<g transform="translate(82,96)">{lm}</g>'.format(lm=mark(lg))
            + '<g transform="translate(238,96)">{rm}</g>'.format(rm=mark(rg))
            + _txt(82, 52, ll) + _txt(238, 52, rl)
            + _txt(160, 144, p.get("cap", "")))
    return _svg(body, vb="0 0 320 152")


def v_radial_roles(p):
    center = p.get("center", "architect")
    roles = p.get("roles", ["support", "support", "support", "support", "support"])
    import math
    n = len(roles)
    body = ""
    for i, r in enumerate(roles):
        a = math.radians(-90 + i * 360 / n)
        x = 160 + 64 * math.cos(a)
        y = 84 + 52 * math.sin(a)
        body += '<line x1="160" y1="84" x2="{x}" y2="{y}" class="edge"/>'.format(x=round(x, 1), y=round(y, 1))
        body += '<circle cx="{x}" cy="{y}" r="8" class="node"/>'.format(x=round(x, 1), y=round(y, 1))
    # hub painted after the spokes; sized to its label, label inverted for contrast
    if len(center) > 9:
        body += '<circle cx="160" cy="84" r="16" class="node hot"/>'
        body += _txt(182, 88, center, cls="lbl sm", anchor="start")
    else:
        r0 = max(16, int(len(center) * 2.6) + 6)
        body += '<circle cx="160" cy="84" r="{r}" class="node hot"/>'.format(r=r0)
        body += _txt(160, 88, center, cls="lbl sm onnode")
    body += _txt(160, 160, p.get("cap", "one mind, amplified by a team"))
    return _svg(body, vb="0 0 320 168")


def v_bridge(p):
    body = ('<rect x="14" y="96" width="92" height="40" class="cliff"/>'
            '<rect x="214" y="96" width="92" height="40" class="cliff"/>'
            '<path d="M106,96 q24,-30 40,-10" class="brokenspan"/>'
            '<path d="M214,96 q-24,-30 -40,-10" class="brokenspan"/>'
            '<line x1="120" y1="78" x2="200" y2="78" class="plank"/>'
            + _txt(60, 124, "design") + _txt(260, 124, "build & use")
            + _txt(160, 158, "AI can re-plank the broken bridge"))
    return _svg(body, vb="0 0 320 166")


def v_channel(p):
    body = ('<rect x="20" y="56" width="70" height="56" rx="10" class="box"/>'
            '<rect x="230" y="56" width="70" height="56" rx="10" class="box"/>'
            + _txt(55, 88, "mind") + _txt(265, 88, "machine")
            + '<path d="M96,72 h128" class="arr thin"/>'
            + '<path d="M218,68 l8,4 l-8,4" class="arrhead2"/>'
            + '<path d="M224,98 h-128" class="arr thick"/>'
            + '<path d="M102,94 l-8,4 l8,4" class="arrhead2"/>'
            + _txt(160, 66, "intent") + _txt(160, 116, "rich feedback")
            + _txt(160, 150, "Mind→Machine, Machine→Mind"))
    return _svg(body, vb="0 0 320 158")


def v_many_to_one(p):
    body = ""
    for i in range(6):
        x = 28 + i * 30
        body += '<rect x="{x}" y="24" width="20" height="44" rx="3" class="silo"/>'.format(x=x)
        body += '<path d="M{x},72 C{x},110 160,96 160,118" class="merge" style="animation-delay:{d}ms"/>'.format(
            x=x + 10, d=i * 90)
    tw = max(84, 7 * len(p.get("target", "")) + 16) if "target" in p else 84  # fit long labels
    body += '<rect x="{x}" y="118" width="{w}" height="30" rx="7" class="box hot"/>'.format(
        x=160 - tw // 2, w=tw)
    body += _txt(160, 138, p.get("target", "one family"))
    body += _txt(160, 164, p.get("cap", "six incompatible lines → System/360"))
    return _svg(body, vb="0 0 320 172")


def v_floor_plan(p):
    body = ('<rect x="40" y="34" width="150" height="100" class="walls"/>'
            '<line x1="40" y1="90" x2="190" y2="90" class="wall load"/>'
            '<rect x="190" y="48" width="86" height="72" class="wing"/>'
            '<path d="M190,84 h86" class="arr small"/>'
            + _txt(115, 160, "new wing flows around load-bearing walls"))
    return _svg(body, vb="0 0 320 170")


def v_verdict_cols(p):
    cols = [("worked", "ok"), ("went wrong", "bad"), ("why", "neutral")]
    body = ""
    for i, (lab, cl) in enumerate(cols):
        x = 24 + i * 100
        body += '<rect x="{x}" y="30" width="80" height="90" rx="8" class="vcol {cl}"/>'.format(x=x, cl=cl)
        body += _txt(x + 40, 78, lab)
    body += _txt(160, 146, "honest post-hoc: what / what not / why")
    return _svg(body, vb="0 0 320 154")


def v_weights(p):
    body = '<line x1="20" y1="120" x2="300" y2="120" class="axis"/>'
    heights = [40, 64, 28, 80, 52]
    for i, h in enumerate(heights):
        x = 40 + i * 50
        body += '<rect x="{x}" y="{y}" width="26" height="{h}" rx="4" class="wbar" style="animation-delay:{d}ms"/>'.format(
            x=x, y=120 - h, h=h, d=i * 140)
    body += _txt(160, 146, p.get("cap", "criteria weights drift; quality shows only at the end"))
    return _svg(body, vb="0 0 320 154")


def v_foggy_contract(p):
    body = ('<rect x="96" y="22" width="128" height="120" rx="6" class="doc"/>')
    for i in range(6):
        body += '<line x1="110" y1="{y}" x2="210" y2="{y}" class="docline fog"/>'.format(y=42 + i * 14)
    body += '<circle cx="200" cy="124" r="13" class="seal"/>'
    body += _txt(160, 158, "a contract signed over fog")
    return _svg(body, vb="0 0 320 166")


def v_define(p):
    body = ('<rect x="40" y="40" width="240" height="58" rx="10" class="card2"/>'
            + _txt(160, 66, p.get("big", "design = the whole process"), cls="lbl big")
            + _txt(160, 86, p.get("sub", "not just the artifact"), cls="lbl sm")
            + _txt(160, 132, p.get("cap", "deciding what to build is the hard part")))
    return _svg(body, vb="0 0 320 148")


def v_network(p):
    return ('<div class="netviz" data-viz="network" data-start="2">'
            '<svg class="dgm net" viewBox="0 0 320 168" role="img" aria-hidden="true">'
            '<g class="nlinks"></g><g class="nnodes"></g></svg>'
            '<p class="netread">' + bl("умов: ", "minds: ")
            + '<b class="nm">2</b> · ' + bl("связей: ", "links: ") + '<b class="nl">1</b></p>'
            '<p class="center"><button class="ctl nadd" type="button">'
            + bl("+1 ум", "+1 mind") + '</button></p>'
            '<p class="vizcap small">' + bl(
                "Каждый новый ум добавляет связи (n(n-1)/2) и размывает единство замысла.",
                "Each new mind adds links (n(n-1)/2) and dilutes conceptual integrity.")
            + '</p></div>')


GEN = {
    "pipeline_vs_loop": v_pipeline_vs_loop, "tree": v_tree, "spiral": v_spiral,
    "funnel": v_funnel, "tug": v_tug, "budget": v_budget, "two_targets": v_two_targets,
    "timeline": v_timeline, "gauge": v_gauge, "principles": v_principles,
    "grid_style": v_grid_style, "arch": v_arch, "view_rays": v_view_rays,
    "line_chart": v_line_chart, "floor_ceiling": v_floor_ceiling, "ladder": v_ladder,
    "cycle": v_cycle, "split": v_split, "radial_roles": v_radial_roles, "bridge": v_bridge,
    "channel": v_channel, "many_to_one": v_many_to_one, "floor_plan": v_floor_plan,
    "verdict_cols": v_verdict_cols, "weights": v_weights, "foggy_contract": v_foggy_contract,
    "define": v_define, "network": v_network,
}

def render_concept_visual(concept, book_dir):
    """Pick the concept's visual. Priority:
       1. a generated illustration (visual.type == 'image') if the file exists;
       2. otherwise the declared visual.component(+visual.params) from book.json.
    Unknown/missing components degrade to an empty visual (never break the build).
    """
    vis = concept.get("visual", {}) or {}
    if vis.get("type") == "image" and vis.get("cache_filename"):
        asset = os.path.join(book_dir, vis["cache_filename"])
        if os.path.isfile(asset) and os.path.getsize(asset) > 0:
            return v_image(vis["cache_filename"], vis.get("alt_ru") or vis.get("title_ru") or "")
    comp = vis.get("component")
    if not comp or comp not in GEN:
        return ""
    params = vis.get("params") or {}
    try:
        return GEN[comp](params)
    except Exception as exc:  # never let one diagram break the build
        return '<!-- viz error {0}: {1} -->'.format(concept.get("id", "?"), esc(exc))


# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #
CSS = """
:root{
  --bg:#f7f8fc; --panel:#ffffff; --ink:#1c2233; --muted:#5b647a;
  --line:#e6e9f2; --brand:#5b8def; --brand-ink:#2d4f9e;
  --green:#3fae5a; --red:#e0533f; --coral:#ff7a59; --teal:#2bb3a3; --gold:#e0a93f;
  --radius:16px; --shadow:0 6px 24px rgba(28,34,51,.08);
  --maxw:900px; font-synthesis:none;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#0f1320; --panel:#171c2b; --ink:#e9ecf6; --muted:#9aa3bd;
         --line:#283149; --brand:#6f9bf0; --brand-ink:#a8c2f7; --shadow:0 6px 24px rgba(0,0,0,.4); }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 20px 96px}
.lang{display:none}
html[lang="ru"] .lang.ru{display:inline}
html[lang="en"] .lang.en{display:inline}
html[lang="ru"] svg text.lang.ru{display:block}
html[lang="en"] svg text.lang.en{display:block}
.t{color:var(--brand-ink);font-weight:600}
a{color:var(--brand-ink)}

/* shared top nav */
header.bar{display:flex;align-items:center;gap:8px 14px;flex-wrap:wrap;padding:10px 20px;
  border-bottom:1px solid var(--line);position:sticky;top:0;z-index:30;
  background:color-mix(in srgb,var(--bg) 86%,transparent);backdrop-filter:blur(8px)}
header.bar a.brandmark{font-weight:800;letter-spacing:.02em;color:var(--brand-ink);text-decoration:none;font-size:1rem}
header.bar .navlinks{display:flex;gap:4px;flex-wrap:wrap}
header.bar .navlinks a{font-size:.85rem;font-weight:600;text-decoration:none;color:var(--muted);
  padding:5px 12px;border-radius:999px;border:1px solid transparent}
header.bar .navlinks a:hover{color:var(--ink);border-color:var(--line);background:var(--panel)}
header.bar .navlinks a.active{color:var(--brand-ink);background:color-mix(in srgb,var(--brand) 14%,transparent)}
header.bar .spacer{flex:1 1 auto}
header.bar .navtag{color:var(--muted);font-size:.8rem;font-weight:500}
.lang-toggle{border:1px solid var(--line);background:var(--panel);color:var(--ink);
  border-radius:999px;padding:7px 16px;font-weight:700;cursor:pointer;font-size:.85rem}
.lang-toggle:hover{border-color:var(--brand)}

/* hero */
.hero{max-width:var(--maxw);margin:0 auto;padding:30px 20px 6px}
.herogrid{display:grid;grid-template-columns:1.3fr 1fr;gap:26px;align-items:center}
@media (max-width:720px){.herogrid{grid-template-columns:1fr}}
.hero .eyebrow{color:var(--brand-ink);font-weight:700;font-size:.8rem;letter-spacing:.06em;text-transform:uppercase}
.hero h1{font-size:clamp(1.8rem,4.4vw,2.7rem);line-height:1.12;margin:.16em 0 .12em;
  background:linear-gradient(90deg,var(--brand-ink),var(--teal));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero .byline{color:var(--muted);font-weight:600;margin:0 0 6px}
.hero p.lead{color:var(--ink);font-size:1.02rem;margin:.4em 0 0;opacity:.92}
.hero .cover{border-radius:var(--radius);border:1px solid var(--line);box-shadow:var(--shadow);
  width:100%;height:auto;display:block}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 2px}
.stats .stat{font-size:.8rem;font-weight:700;color:var(--brand-ink);
  background:color-mix(in srgb,var(--brand) 12%,transparent);border:1px solid var(--line);
  border-radius:999px;padding:5px 13px;font-variant-numeric:tabular-nums}

/* parts strip */
.parts{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0 0}
.parts .pchip{font-size:.78rem;font-weight:600;color:var(--muted);background:var(--panel);
  border:1px solid var(--line);border-radius:10px;padding:7px 12px}
.parts .pchip b{color:var(--brand-ink)}

/* section TOC */
.toc{display:flex;gap:7px;flex-wrap:wrap;margin:26px 0 0;padding:14px;border:1px solid var(--line);
  border-radius:var(--radius);background:var(--panel);box-shadow:var(--shadow)}
.toc a{font-size:.8rem;font-weight:600;text-decoration:none;color:var(--muted);
  padding:5px 11px;border-radius:999px;border:1px solid var(--line)}
.toc a:hover{color:var(--brand-ink);border-color:var(--brand)}

/* section + concept */
.section{margin:46px 0 0;scroll-margin-top:64px}
.section>h2{font-size:clamp(1.3rem,3vw,1.7rem);margin:0;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.section>h2 .snum{display:inline-grid;place-items:center;min-width:30px;height:30px;border-radius:9px;
  background:var(--brand-ink);color:#fff;font-size:.9rem;font-weight:800;padding:0 8px}
.section .intro{color:var(--muted);margin:10px 0 0;max-width:70ch}
.section .srcrow{margin:10px 0 0;display:flex;gap:8px;flex-wrap:wrap}
.section .srcrow a{font-size:.76rem;font-weight:600;text-decoration:none;color:var(--brand-ink);
  border:1px solid var(--line);border-radius:999px;padding:4px 11px}
.section .srcrow a:hover{border-color:var(--brand)}

.concept{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:22px 24px;margin:18px 0}
.concept h3{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 2px;font-size:1.04rem}
.idx{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:50%;
  background:var(--brand);color:#fff;font-size:.8rem;font-weight:700;flex:0 0 auto}
.term-en{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em;
  background:color-mix(in srgb,var(--brand) 15%,transparent);color:var(--brand-ink);padding:.06em .45em;border-radius:7px}
.concept p.body{margin:12px 0 0}
.analogy{margin:13px 0 0;padding:11px 15px;border-radius:12px;
  background:color-mix(in srgb,var(--coral) 12%,transparent);border:1px dashed var(--coral)}
.analogy::before{content:"🧩 "}
blockquote.quote{margin:13px 0 0;padding:10px 16px;border-left:3px solid var(--teal);
  background:color-mix(in srgb,var(--teal) 9%,transparent);border-radius:0 10px 10px 0;
  font-style:italic;color:var(--ink)}
blockquote.quote::before{content:"\\201C"}
blockquote.quote::after{content:"\\201D \\2014 __QUOTE_AUTHOR__"}
.viz{margin:16px 0 0;padding:16px;border-radius:12px;background:var(--bg);border:1px solid var(--line)}
.vizcap{color:var(--muted);font-size:.86rem;margin:10px 0 0;text-align:center}
.vizcap.small{font-size:.8rem}
.imgfig{margin:0}
.imgfig img{width:100%;height:auto;border-radius:10px;border:1px solid var(--line);display:block}

/* diagrams */
svg.dgm{width:100%;height:auto;max-height:230px;display:block;margin:0 auto}
svg text{fill:var(--muted);font-size:11px;font-weight:600;font-family:inherit}
svg text.sm{font-size:9px}
svg text.onnode{fill:var(--panel);font-weight:700}
svg text.big{font-size:13px;font-weight:800;fill:var(--ink)}
svg text.lang{display:none}
.box{fill:color-mix(in srgb,var(--brand) 16%,var(--panel));stroke:var(--brand);stroke-width:1.5}
.box.hot{fill:color-mix(in srgb,var(--brand) 30%,var(--panel));stroke:var(--brand-ink)}
.box.left{fill:color-mix(in srgb,var(--brand) 20%,var(--panel))}
.box.right{fill:color-mix(in srgb,var(--coral) 20%,var(--panel));stroke:var(--coral)}
.arr{stroke:var(--muted);stroke-width:1.6;fill:none;marker-end:none}
.arr.small{stroke-width:1.2}
.arr.thin{stroke:var(--brand);stroke-width:1.6;fill:none}
.arr.thick{stroke:var(--teal);stroke-width:3.2;fill:none}
.arr.up{stroke:var(--green);stroke-width:2;fill:none}
.arr.up.hot{stroke:var(--coral)}
.arr.back{stroke:var(--gold);stroke-width:1.8;fill:none;stroke-dasharray:4 3}
.arrhead{fill:none;stroke:var(--muted);stroke-width:1.6}
.arrhead2{fill:none;stroke-width:1.8}
.arr.thin+.arrhead2,.arrhead2{stroke:var(--brand)}
.node{fill:var(--brand);stroke:var(--panel);stroke-width:1.5;transform-box:fill-box;transform-origin:center;
  animation:pop .4s cubic-bezier(.34,1.56,.64,1) both}
.node.hot{fill:var(--brand-ink)}
.node.dead{fill:var(--red)}
.node.grow{animation:pop .4s ease both}
.edge{stroke:#9fb6e8;stroke-width:1.4}
.edge.hot{stroke:var(--brand-ink);stroke-width:2.4}
.edge.dead{stroke:var(--red);stroke-dasharray:4 3;opacity:.7}
.crack{stroke:var(--red);stroke-width:1.6;fill:none}
.spiral{fill:none;stroke:var(--brand);stroke-width:2.2;stroke-linecap:round}
.spiral.two{stroke:var(--teal)}
.ring{fill:none;stroke:var(--brand);stroke-width:2;opacity:.5;transform-box:fill-box;transform-origin:center;
  animation:pulse 2.4s ease-in-out infinite}
.loopring{fill:none;stroke:var(--line);stroke-width:2}
.loopdash{fill:none;stroke:var(--teal);stroke-width:2.6;stroke-linecap:round;stroke-dasharray:240;
  stroke-dashoffset:240;animation:draw 1.6s ease forwards}
.funnel{fill:color-mix(in srgb,var(--brand) 12%,var(--panel));stroke:var(--brand);stroke-width:1.6}
.drop{fill:var(--coral);animation:fall 2.4s ease-in-out infinite}
.drop.keep{fill:var(--green);animation:none}
.rope{stroke:var(--gold);stroke-width:3;stroke-linecap:round}
.knot{fill:var(--gold);animation:tug 2.6s ease-in-out infinite}
.ring2{fill:none;stroke:var(--teal);stroke-width:2}
.ring2.fog{stroke:var(--muted);opacity:.45;filter:blur(1px)}
.hit{fill:var(--coral)}
.axis{stroke:var(--line);stroke-width:1.6}
.plan{stroke:var(--green);stroke-width:3}
.slip{stroke:var(--red);stroke-width:3;stroke-dasharray:5 3}
.person{fill:var(--brand)}
.freeze{fill:color-mix(in srgb,var(--brand) 18%,var(--panel));stroke:var(--brand)}
.flex{fill:color-mix(in srgb,var(--teal) 16%,var(--panel));stroke:var(--teal)}
.gaugebg{fill:none;stroke:var(--line);stroke-width:10;stroke-linecap:round}
.gaugefill{fill:none;stroke:var(--teal);stroke-width:10;stroke-linecap:round;stroke-dasharray:300;
  stroke-dashoffset:300;animation:draw 1.6s ease forwards}
.needle{stroke:var(--brand-ink);stroke-width:3;stroke-linecap:round;
  transform-origin:160px 130px;animation:swing 2.8s ease-in-out infinite alternate}
.pivot{fill:var(--brand-ink)}
.cell{fill:color-mix(in srgb,var(--brand) 16%,var(--panel));stroke:var(--brand);stroke-width:1.2}
.arch{fill:none;stroke:var(--brand);stroke-width:6;stroke-linecap:round}
.keystone{fill:var(--gold);stroke:var(--brand-ink);stroke-width:1.4}
.sheet{fill:var(--panel);stroke:var(--line);stroke-width:1.4}
.line2{stroke:var(--muted);stroke-width:1.4}
.house{fill:color-mix(in srgb,var(--teal) 16%,var(--panel));stroke:var(--teal);stroke-width:1.6}
.ray{stroke:var(--gold);stroke-width:1.6;opacity:.8;stroke-dasharray:160;stroke-dashoffset:160;
  animation:draw 1.4s ease forwards}
.curve{fill:none;stroke:var(--brand);stroke-width:3;stroke-linecap:round;stroke-dasharray:400;
  stroke-dashoffset:400;animation:draw 1.8s ease forwards}
.band{fill:color-mix(in srgb,var(--brand) 8%,var(--panel));stroke:var(--line)}
.floor{stroke:var(--green);stroke-width:3}
.ceil{stroke:var(--coral);stroke-width:3}
.rail{stroke:var(--brand);stroke-width:2.4;stroke-linecap:round}
.rung{stroke:var(--brand);stroke-width:2.4;stroke-linecap:round;animation:fadeup .4s ease both}
.bridge2{stroke:var(--teal);stroke-width:2;stroke-dasharray:4 3}
.pane{fill:var(--panel);stroke-width:1.6}
.pane.good{stroke:var(--green);fill:color-mix(in srgb,var(--green) 8%,var(--panel))}
.pane.bad{stroke:var(--red);fill:color-mix(in srgb,var(--red) 8%,var(--panel))}
.ok{fill:none;stroke:var(--green);stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
.bad{fill:none;stroke:var(--red);stroke-width:3;stroke-linecap:round}
.silo{fill:color-mix(in srgb,var(--muted) 22%,var(--panel));stroke:var(--muted);stroke-width:1.2}
.merge{fill:none;stroke:var(--brand);stroke-width:1.6;stroke-dasharray:200;stroke-dashoffset:200;
  animation:draw 1.6s ease forwards}
.walls{fill:none;stroke:var(--brand);stroke-width:2}
.wall.load{stroke:var(--red);stroke-width:3}
.wing{fill:color-mix(in srgb,var(--teal) 14%,var(--panel));stroke:var(--teal);stroke-width:2}
.vcol{stroke-width:1.6}
.vcol.ok{fill:color-mix(in srgb,var(--green) 12%,var(--panel));stroke:var(--green)}
.vcol.bad{fill:color-mix(in srgb,var(--red) 12%,var(--panel));stroke:var(--red)}
.vcol.neutral{fill:color-mix(in srgb,var(--brand) 12%,var(--panel));stroke:var(--brand)}
.wbar{fill:color-mix(in srgb,var(--brand) 30%,var(--panel));stroke:var(--brand);stroke-width:1.2;
  animation:growbar .7s ease both;transform-box:fill-box;transform-origin:bottom}
.doc{fill:var(--panel);stroke:var(--line);stroke-width:1.6}
.docline{stroke:var(--muted);stroke-width:2}
.docline.fog{opacity:.4;filter:blur(1.2px)}
.seal{fill:color-mix(in srgb,var(--red) 30%,var(--panel));stroke:var(--red);stroke-width:1.4}
.card2{fill:var(--panel);stroke:var(--brand);stroke-width:1.6}
.cliff{fill:color-mix(in srgb,var(--muted) 22%,var(--panel))}
.brokenspan{fill:none;stroke:var(--muted);stroke-width:3}
.plank{stroke:var(--teal);stroke-width:3;stroke-dasharray:5 3;animation:draw 1.4s ease forwards;
  stroke-dashoffset:90}

@keyframes pop{from{transform:scale(.3);opacity:0}to{transform:scale(1);opacity:1}}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes pulse{0%,100%{opacity:.25}50%{opacity:.6}}
@keyframes fall{0%{transform:translateY(0);opacity:1}70%{transform:translateY(96px);opacity:.3}100%{opacity:0}}
@keyframes tug{0%,100%{transform:translateX(-9px)}50%{transform:translateX(9px)}}
@keyframes swing{from{transform:rotate(-22deg)}to{transform:rotate(20deg)}}
@keyframes fadeup{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes growbar{from{transform:scaleY(0)}to{transform:scaleY(1)}}

/* interactive: network + budget */
.netviz .net{max-height:200px}
.netread{text-align:center;margin:6px 0 2px}.netread b{font-variant-numeric:tabular-nums;color:var(--brand-ink)}
button.ctl{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:10px;
  padding:8px 15px;font-weight:600;cursor:pointer}
button.ctl:hover{border-color:var(--brand)}
.center{text-align:center}
.budget .bbar{display:flex;height:34px;border-radius:9px;overflow:hidden;border:1px solid var(--line)}
.budget .seg{display:grid;place-items:center;color:#fff;font-size:.72rem;font-weight:700;
  transition:width .15s ease;overflow:hidden;white-space:nowrap}
.budget .seg.s1{background:var(--brand)}.budget .seg.s2{background:var(--teal)}
.budget .seg.s3{background:var(--coral)}.budget .seg.s4{background:var(--muted)}
.budget .brow{text-align:center;margin:8px 0 2px;font-size:.85rem}
.budget .bslider{width:100%;accent-color:var(--brand)}

/* glossary */
.glossary{margin:46px 0 0}
.gsearch{width:100%;padding:11px 15px;border:1px solid var(--line);border-radius:12px;background:var(--panel);
  color:var(--ink);font-size:.95rem;margin:12px 0 6px}
.gsearch:focus{outline:none;border-color:var(--brand)}
.gnone{color:var(--muted);font-size:.9rem;display:none;padding:8px 2px}
.glist{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0 0}
@media (max-width:640px){.glist{grid-template-columns:1fr}}
.gterm{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 16px}
.gterm .gt{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:700;color:var(--brand-ink);font-size:.92rem}
.gterm .gd{color:var(--muted);font-size:.9rem;margin-top:4px}

/* Q&A */
.qa{margin:46px 0 0}
.qcard{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin:10px 0;overflow:hidden}
.qcard summary{cursor:pointer;padding:14px 16px;font-weight:600;display:flex;gap:10px;align-items:flex-start;list-style:none}
.qcard summary::-webkit-details-marker{display:none}
.qcard summary::before{content:"?";flex:0 0 auto;width:24px;height:24px;border-radius:50%;
  background:var(--brand);color:#fff;display:grid;place-items:center;font-weight:800;font-size:.8rem}
.qcard[open] summary::before{content:"\\2713";background:var(--green)}
.qdiff{margin-left:auto;font-size:.7rem;font-weight:800;text-transform:uppercase;letter-spacing:.04em;
  padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.qdiff.easy{color:var(--green)}.qdiff.medium{color:var(--gold)}.qdiff.hard{color:var(--coral)}
.qbody{padding:0 16px 16px 50px;border-top:1px solid var(--line);margin-top:0}
.qbody .qhint{color:var(--muted);font-size:.82rem;margin:10px 0 4px}
.qbody ul{margin:4px 0 0;padding-left:1.1em}.qbody li{margin:6px 0}

.endcta{margin:48px 0 0;background:linear-gradient(135deg,color-mix(in srgb,var(--brand) 12%,var(--panel)),var(--panel));
  border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px 24px;
  display:flex;align-items:center;gap:16px;flex-wrap:wrap;justify-content:space-between}
.endcta p{margin:0;font-weight:600}
.endcta a.btn{text-decoration:none;font-weight:700;font-size:.9rem;color:#fff;
  background:linear-gradient(90deg,var(--brand),var(--teal));border-radius:999px;padding:10px 20px}
h2.blk{font-size:clamp(1.3rem,3vw,1.7rem);margin:0}

@media (prefers-reduced-motion: reduce){
  *{animation-duration:.001s!important;animation-iteration-count:1!important;transition:none!important}
  .loopdash,.gaugefill,.curve,.merge,.ray,.plank{stroke-dashoffset:0!important}
}
"""

# --------------------------------------------------------------------------- #
# JS
# --------------------------------------------------------------------------- #
JS = """
(function(){
  var KEY='deepdive-lang';
  var lang=localStorage.getItem(KEY)||'ru';
  var btn=document.getElementById('langToggle');
  function apply(){
    document.documentElement.setAttribute('lang',lang);
    if(btn) btn.textContent= lang==='ru' ? 'EN' : 'RU';
  }
  if(btn) btn.addEventListener('click',function(){ lang= lang==='ru'?'en':'ru'; localStorage.setItem(KEY,lang); apply(); });
  apply();

  /* glossary live filter */
  var gs=document.getElementById('gsearch');
  if(gs){
    var items=[].slice.call(document.querySelectorAll('.gterm'));
    var none=document.getElementById('gnone');
    gs.addEventListener('input',function(){
      var q=gs.value.trim().toLowerCase(),shown=0;
      items.forEach(function(it){
        var hit=it.getAttribute('data-k').indexOf(q)>=0;
        it.style.display=hit?'':'none'; if(hit)shown++;
      });
      if(none) none.style.display=shown?'none':'block';
    });
  }

  /* interactive collaboration network */
  [].slice.call(document.querySelectorAll('.netviz')).forEach(function(box){
    var L=box.querySelector('.nlinks'),N=box.querySelector('.nnodes');
    var nm=box.querySelector('.nm'),nl=box.querySelector('.nl'),add=box.querySelector('.nadd');
    var cx=160,cy=80,r=58,count=parseInt(box.getAttribute('data-start')||'2',10);
    function render(n){
      var c=[];N.innerHTML='';L.innerHTML='';
      for(var k=0;k<n;k++){var a=(k/n)*2*Math.PI-Math.PI/2,x=cx+r*Math.cos(a),y=cy+r*Math.sin(a);c.push([x,y]);}
      var d=0;
      for(var i=0;i<n;i++)for(var j=i+1;j<n;j++){
        var ln=document.createElementNS('http://www.w3.org/2000/svg','line');
        ln.setAttribute('x1',c[i][0]);ln.setAttribute('y1',c[i][1]);ln.setAttribute('x2',c[j][0]);ln.setAttribute('y2',c[j][1]);
        ln.setAttribute('class','edge'+(n>=5?' hot':''));ln.style.strokeWidth=(n>=5?'1.8':'1.2');L.appendChild(ln);d++;}
      for(var m=0;m<n;m++){var cc=document.createElementNS('http://www.w3.org/2000/svg','circle');
        cc.setAttribute('cx',c[m][0]);cc.setAttribute('cy',c[m][1]);cc.setAttribute('r',9);
        cc.setAttribute('class','node'+(m===0?' hot':''));cc.style.animationDelay=(m*40)+'ms';N.appendChild(cc);}
      if(nm)nm.textContent=n; if(nl)nl.textContent=n*(n-1)/2;
    }
    render(count);
    if(add)add.addEventListener('click',function(){count=Math.min(count+1,9);render(count);});
  });

  /* interactive budgeted resource */
  [].slice.call(document.querySelectorAll('.budget')).forEach(function(box){
    var sl=box.querySelector('.bslider'),s1=box.querySelector('.s1'),s4=box.querySelector('.s4');
    if(!sl)return;
    sl.addEventListener('input',function(){
      var v=+sl.value; s1.style.width=v+'%';
      var spare=Math.max(0,100-v-26-22); s4.style.width=spare+'%';
      s4.textContent= spare<8 ? 'over!' : 'spare';
      s4.style.background= spare<8 ? 'var(--red)' : 'var(--muted)';
    });
  });
})();
"""


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def nav_html(brandmark="", navtag=""):
    """Standalone top bar: book title as brandmark + a RU/EN toggle. No cross-page links."""
    return (
        '<header class="bar">'
        '<a class="brandmark" href="#">{brand}</a>'
        '<span class="spacer"></span>'
        '<small class="navtag">{tag}</small>'
        '<button id="langToggle" class="lang-toggle" type="button">EN</button>'
        '</header>'
    ).format(brand=esc(brandmark), tag=esc(navtag))


def hero_html(book, has_cover):
    b = book.get("book", {})
    nconc = sum(len(s["concepts"]) for s in book["sections"])
    nparts = len(book.get("parts", []))
    nsec = len(book["sections"])
    byline = " · ".join(x for x in [b.get("author", ""), b.get("subtitle_en", ""), str(b.get("year", "") or "")] if x)
    cover = ('<div><img class="cover" src="assets/cover.png" alt="'
             + esc(b.get("cover_alt_ru", "Обложка-иллюстрация книги.")) + '"></div>') if has_cover else ''
    return (
        '<section class="hero"><div class="herogrid">'
        '<div>'
        '<div class="eyebrow">' + bl("Разбор книги", "Book deep-dive") + '</div>'
        '<h1>' + esc(b.get("title_en", "")) + '</h1>'
        '<p class="byline">' + esc(byline) + '</p>'
        '<p class="lead">' + bl(esc(book["summary_ru"]), esc(book["summary_en"])) + '</p>'
        '<div class="stats">'
        + (('<span class="stat">' + bl(str(nparts) + " частей", str(nparts) + " parts") + '</span>') if nparts else '')
        + '<span class="stat">' + bl(str(nsec) + " тем", str(nsec) + " themes") + '</span>'
        '<span class="stat">' + bl(str(nconc) + " концептов", str(nconc) + " concepts") + '</span>'
        '<span class="stat">' + bl(str(len(book["glossary"])) + " терминов", str(len(book["glossary"])) + " terms") + '</span>'
        '</div>'
        '</div>'
        + cover +
        '</div></section>'
    )


def parts_html(book):
    chips = ['<div class="eyebrow" style="color:var(--muted)">' + bl("Структура книги", "Book structure") + '</div>']
    chips.append('<div class="parts">')
    for p in book.get("parts", []):
        chips.append('<div class="pchip"><b>' + bl("Часть " + str(p["number"]), "Part " + str(p["number"])) + '</b> · '
                     + bl(esc(p["title_ru"]), esc(p["title_en"])) + '</div>')
    chips.append('</div>')
    return '<section style="margin-top:24px">' + "".join(chips) + '</section>'


def toc_html(book):
    out = ['<nav class="toc">']
    for i, s in enumerate(book["sections"], 1):
        out.append('<a href="#sec-{id}">{n}. {t}</a>'.format(
            id=esc(s["id"]), n=i, t=bl(esc(s["title_ru"]), esc(s["title_en"]))))
    out.append('<a href="#glossary">' + bl("Глоссарий", "Glossary") + '</a>')
    out.append('<a href="#qa">' + bl("Проверь себя", "Self-check") + '</a>')
    out.append('</nav>')
    return "".join(out)


def concept_html(concept, idx, book_dir):
    vis = concept.get("visual", {})
    parts = ['<article class="concept" id="c-{0}">'.format(esc(concept["id"]))]
    parts.append('<h3><span class="idx">{0}</span><span class="term-en">{1}</span></h3>'.format(
        idx, esc(concept["term_en"])))
    parts.append('<p class="body">' + bl(hl(concept["explanation_ru"]), hl(concept["explanation_en"])) + '</p>')
    if concept.get("analogy_ru"):
        parts.append('<p class="analogy">' + bl(esc(concept["analogy_ru"]), esc(concept.get("analogy_en") or concept["analogy_ru"])) + '</p>')
    if concept.get("quote_en"):
        parts.append('<blockquote class="quote">' + esc(concept["quote_en"]) + '</blockquote>')
    viz = render_concept_visual(concept, book_dir)
    if viz:
        cap = bl(esc(vis.get("title_ru", "")), esc(vis.get("title_en") or vis.get("title_ru", "")))
        parts.append('<div class="viz">' + viz + '<p class="vizcap">' + cap + '</p></div>')
    parts.append('</article>')
    return "".join(parts)


def section_html(book, section, num, book_dir):
    out = ['<section class="section" id="sec-{0}">'.format(esc(section["id"]))]
    out.append('<h2><span class="snum">{0}</span>{1}</h2>'.format(
        num, bl(esc(section["title_ru"]), esc(section["title_en"]))))
    out.append('<p class="intro">' + bl(esc(section["intro_ru"]), esc(section["intro_en"])) + '</p>')
    srcs = section.get("source_docs") or []
    if srcs:
        row = ['<div class="srcrow">']
        for sd in srcs:
            row.append('<a href="sources/{0}">{1}</a>'.format(esc(sd), bl("📄 глубокий разбор", "📄 deep-dive notes")))
        row.append('</div>')
        out.append("".join(row))
    for i, c in enumerate(section["concepts"], 1):
        out.append(concept_html(c, i, book_dir))
    out.append('</section>')
    return "".join(out)


def glossary_html(book):
    out = ['<section class="glossary" id="glossary">']
    out.append('<h2 class="blk">' + bl("Глоссарий книги", "Book glossary") + '</h2>')
    out.append('<input id="gsearch" class="gsearch" type="search" placeholder="'
               + "поиск термина… / filter terms…" + '" aria-label="filter">')
    out.append('<p id="gnone" class="gnone">' + bl("Ничего не найдено.", "No matches.") + '</p>')
    out.append('<div class="glist">')
    for g in book["glossary"]:
        key = esc((g["term_en"] + " " + g.get("definition_ru", "") + " " + g.get("definition_en", "")).lower())
        out.append('<div class="gterm" data-k="{k}"><div class="gt">{t}</div><div class="gd">{d}</div></div>'.format(
            k=key, t=esc(g["term_en"]),
            d=bl(esc(g["definition_ru"]), esc(g.get("definition_en") or g["definition_ru"]))))
    out.append('</div></section>')
    return "".join(out)


def qa_html(book):
    out = ['<section class="qa" id="qa">']
    out.append('<h2 class="blk">' + bl("Проверь себя", "Self-check") + '</h2>')
    out.append('<p class="intro">' + bl(
        "Активное повторение: ответь про себя, затем раскрой опорные пункты.",
        "Active recall: answer in your head, then reveal the key points.") + '</p>')
    for q in book["qa_seeds"]:
        diff = q.get("difficulty", "medium")
        out.append('<details class="qcard"><summary>'
                   + bl(esc(q["question_ru"]), esc(q.get("question_en") or q["question_ru"]))
                   + '<span class="qdiff {d}">{d}</span></summary>'.format(d=esc(diff)))
        out.append('<div class="qbody"><p class="qhint">' + bl("Опорные пункты ответа:", "Key points:") + '</p><ul>')
        pts_ru = q.get("expected_answer_points", [])
        pts_en = q.get("expected_answer_points_en", []) or pts_ru
        for i, pr in enumerate(pts_ru):
            pe = pts_en[i] if i < len(pts_en) else pr
            out.append('<li>' + bl(esc(pr), esc(pe)) + '</li>')
        out.append('</ul></div></details>')
    out.append('</section>')
    return "".join(out)


def short_author(name):
    """'Frederick P. Brooks Jr.' -> 'F. Brooks' for the compact navtag."""
    if not name:
        return ""
    parts = [p for p in name.replace(" Jr.", "").replace(" Sr.", "").split() if p]
    return "{0}. {1}".format(parts[0][:1].upper(), parts[-1]) if len(parts) >= 2 else name


def author_surname(name):
    """'Frederick P. Brooks Jr.' -> 'Brooks'; 'G. W. F. Hegel' -> 'Hegel'.
    Used for the per-quote attribution suffix (data-driven, not hardcoded)."""
    if not name:
        return ""
    parts = [p for p in name.replace(" Jr.", "").replace(" Sr.", "").split() if p]
    return parts[-1] if parts else name


def render_html(book, book_dir):
    build_highlighter([g["term_en"] for g in book.get("glossary", [])]
                      + [c["term_en"] for s in book["sections"] for c in s["concepts"]])
    b = book.get("book", {})
    title = b.get("title_en") or "Book"
    navtag = " · ".join(x for x in [short_author(b.get("author", "")), str(b.get("year", "") or "")] if x)
    has_cover = os.path.isfile(os.path.join(book_dir, "assets", "cover.png"))
    css = CSS.replace("__QUOTE_AUTHOR__", esc(author_surname(b.get("author", ""))))
    out = ['<!doctype html>', '<html lang="ru">', '<head>',
           '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>' + esc(title) + '</title>',
           '<style>', css, '</style>', '</head>', '<body>']
    out.append(nav_html(b.get("title_ru") or b.get("title_en") or "Book", navtag))
    out.append(hero_html(book, has_cover))
    out.append('<main class="wrap">')
    out.append(parts_html(book))
    out.append(toc_html(book))
    for i, s in enumerate(book["sections"], 1):
        out.append(section_html(book, s, i, book_dir))
    out.append(glossary_html(book))
    out.append(qa_html(book))
    out.append('<div class="endcta"><p>' + bl(
        "Конец разбора. Переключите язык в шапке или вернитесь к оглавлению выше.",
        "End of the deep-dive. Toggle the language in the header, or jump back to the table of contents above.")
        + '</p></div>')
    out.append('</main>')
    out.append('<script>' + JS + '</script>')
    out.append('</body></html>')
    return "\n".join(out)


def build_one(book_dir):
    book_dir = os.path.abspath(book_dir)
    slug = os.path.basename(book_dir.rstrip(os.sep))
    book = load(book_dir)
    out_path = os.path.join(book_dir, slug + ".html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(book, book_dir))
    print("Wrote:", out_path,
          "| sections:", len(book["sections"]),
          "concepts:", sum(len(s["concepts"]) for s in book["sections"]),
          "glossary:", len(book["glossary"]), "qa:", len(book["qa_seeds"]))


def discover_book_dirs(root):
    import glob as _glob
    return [os.path.dirname(p) for p in sorted(_glob.glob(os.path.join(root, "books", "*", "book.json")))]


def main(argv):
    targets = [a for a in argv if not a.startswith("-")]
    if targets:
        dirs = [(t if os.path.isdir(t) else os.path.dirname(t)) for t in targets]
    else:
        dirs = discover_book_dirs(find_root())
    if not dirs:
        print("No book.json found under books/*/")
        return
    for d in dirs:
        build_one(d)


if __name__ == "__main__":
    main(sys.argv[1:])
