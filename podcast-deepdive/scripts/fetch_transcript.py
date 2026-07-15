#!/usr/bin/env python3
"""
fetch_transcript.py — выкачка транскрипта YouTube-эпизода для скилла podcast-deepdive.

stdlib-only по импортам; внешний CLI `yt-dlp` — пред-реквизит (как headless-Chrome
для скриншотов). Если бинаря `yt-dlp` нет в PATH, пробуем `python3 -m yt_dlp`.

Что делает:
  1. Тянет метаданные эпизода (--dump-json): title, channel, duration, chapters,
     description, upload_date.
  2. Тянет субтитры: предпочитает РУЧНЫЕ (manual) субтитры; если их нет — авто
     (--write-auto-subs). Пишет captions_kind = "manual" | "auto".
  3. Парсит VTT в чистый MM:SS-транскрипт (снимает «бегущее окно», inline word-timing
     теги и HTML-сущности; сохраняет маркеры смены говорящего ">>").
  4. Кладёт <slug>.txt (транскрипт) и episode_seed.json (метаданные + подсказки
     по спикерам из description) в <out_dir>.

Использование:
  python3 fetch_transcript.py <youtube-url> <out_dir> [--slug NAME] [--gap SECONDS]

Дальше пайплайн (analyze → build_page) — чистый stdlib.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


# ---------- yt-dlp invocation ----------

def yt_dlp_cmd():
    """Вернуть базовую команду для запуска yt-dlp (бинарь или python -m)."""
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    # fallback: модуль (pip install --user yt-dlp)
    return [sys.executable, "-m", "yt_dlp"]


def run_yt_dlp(args, **kw):
    cmd = yt_dlp_cmd() + args
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def fetch_metadata(url):
    r = run_yt_dlp(["--skip-download", "--dump-json", url])
    if r.returncode != 0:
        sys.exit("yt-dlp metadata failed:\n" + (r.stderr or "")[-2000:])
    return json.loads(r.stdout)


def fetch_subtitles(url, workdir, vid):
    """Скачать субтитры. Возвращает (path_to_vtt, kind) либо (None, None)."""
    out_tmpl = os.path.join(workdir, "%(id)s.%(ext)s")
    # 1) сначала пробуем РУЧНЫЕ субтитры (чистые)
    for langs in ("en,en-US,en-GB", "en.*"):
        r = run_yt_dlp(["--skip-download", "--write-subs", "--sub-langs", langs,
                        "--sub-format", "vtt", "-o", out_tmpl, url])
        vtt = _find_vtt(workdir, vid)
        if vtt:
            return vtt, "manual"
    # 2) иначе авто-субтитры (предпочитаем оригинальную дорожку en-orig)
    for langs in ("en-orig", "en"):
        run_yt_dlp(["--skip-download", "--write-auto-subs", "--sub-langs", langs,
                    "--sub-format", "vtt", "-o", out_tmpl, url])
        vtt = _find_vtt(workdir, vid)
        if vtt:
            return vtt, "auto"
    return None, None


def _find_vtt(workdir, vid):
    cands = [f for f in os.listdir(workdir) if f.startswith(vid) and f.endswith(".vtt")]
    if not cands:
        return None
    # предпочесть en-orig, затем en, затем любой
    cands.sort(key=lambda f: (".en-orig." not in f, ".en." not in f, f))
    return os.path.join(workdir, cands[0])


# ---------- VTT parsing ----------

_TS = re.compile(r'(\d\d):(\d\d):(\d\d)\.(\d\d\d)\s+-->\s+(\d\d):(\d\d):(\d\d)\.(\d\d\d)')
_INLINE = re.compile(r'<\d\d:\d\d:\d\d\.\d\d\d>')
_CTAG = re.compile(r'</?c[^>]*>')


def parse_vtt(text):
    """VTT -> список (start_sec, clean_text).

    АВТО-субтитры несут inline word-timing теги <00:00:00.000>: канонический «новый»
    текст только в тегированных cue, осевшие дубли без тегов пропускаем (снимает бегущее
    окно). РУЧНЫЕ субтитры тегов НЕ имеют — там каждый cue уникален и многострочен, берём
    все, склеивая строки. Режим определяем по наличию тегов во всём файле.
    """
    has_inline = bool(_INLINE.search(text))
    cues = []
    for block in re.split(r'\n\n+', text):
        lines = block.splitlines()
        start = None
        body = []
        for ln in lines:
            m = _TS.search(ln)
            if m and start is None:
                h, mi, s, ms = (int(m.group(i)) for i in range(1, 5))
                start = h * 3600 + mi * 60 + s + ms / 1000.0
            elif start is not None:
                body.append(ln)
        if start is None:
            continue
        if has_inline:
            tagged = next((b for b in body if _INLINE.search(b)), None)
            if tagged is None:
                # осевший дубль без тегов — пропускаем, кроме самого первого cue файла
                if cues:
                    continue
                cand = [b for b in body if b.strip()]
                if not cand:
                    continue
                tagged = cand[-1]
            clean = _CTAG.sub('', _INLINE.sub('', tagged))
        else:
            # ручные субтитры: склеиваем все строки текста cue
            clean = _CTAG.sub('', " ".join(b.strip() for b in body if b.strip()))
        clean = html.unescape(clean).strip()
        if not clean:
            continue
        if cues and cues[-1][1] == clean:   # точный дубль подряд
            continue
        cues.append((start, clean))
    return cues


def reflow(cues, gap=18.0):
    """Склеить мелкие cue в читаемые строки 'MM:SS текст'.

    Новая строка начинается при смене говорящего (маркер '>>') ИЛИ когда с начала
    текущей строки прошло >= gap секунд. Маркер '>>' сохраняется в начале строки.
    """
    out = []
    cur_start = None
    buf = []
    turn_flag = False

    def flush():
        if buf:
            mm, ss = int(cur_start // 60), int(cur_start % 60)
            prefix = ">> " if turn_flag else ""
            out.append("%02d:%02d %s%s" % (mm, ss, prefix, " ".join(buf).strip()))

    for start, txt in cues:
        t = txt.lstrip()
        is_turn = t.startswith(">>")
        if is_turn:
            t = t[2:].strip()
        if cur_start is None:
            cur_start, turn_flag = start, is_turn
        elif is_turn or (start - cur_start >= gap):
            flush()
            buf = []
            cur_start, turn_flag = start, is_turn
        buf.append(t)
    flush()
    return out


# ---------- speaker hints ----------

def speaker_hints(meta):
    """Грубые подсказки по участникам из channel + description (для агента анализа).
    Имена НЕ закрепляются жёстко — финальную атрибуцию делает анализ по контексту."""
    host = meta.get("channel") or meta.get("uploader") or ""
    desc = meta.get("description") or ""
    # эвристика: ищем '<Имя> is the founder/CEO/...' в первых строках
    guests = re.findall(r'([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})\s+is\s+(?:the\s+|a\s+|an\s+)', desc)
    seen, uniq = set(), []
    for g in guests:
        if g not in seen and g != host:
            seen.add(g)
            uniq.append(g)
    return {"host_hint": host, "guest_hints": uniq[:4]}


def hhmmss(sec):
    sec = int(sec or 0)
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out_dir")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--gap", type=float, default=18.0,
                    help="секунд на одну строку транскрипта (по умолч. 18)")
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    slug = a.slug or os.path.basename(os.path.normpath(a.out_dir))

    print("· метаданные…")
    meta = fetch_metadata(a.url)
    vid = meta.get("id")

    with tempfile.TemporaryDirectory() as tmp:
        print("· субтитры…")
        vtt, kind = fetch_subtitles(a.url, tmp, vid)
        if not vtt:
            sys.exit("Субтитры не найдены (ни ручные, ни авто). "
                     "Вставь транскрипт вручную в %s.txt" % os.path.join(a.out_dir, slug))
        raw = open(vtt, encoding="utf-8").read()

    cues = parse_vtt(raw)
    lines = reflow(cues, gap=a.gap)
    txt_path = os.path.join(a.out_dir, slug + ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    chapters = [{"t_seconds": int(c.get("start_time", 0)),
                 "title_en": c.get("title", "")} for c in (meta.get("chapters") or [])]
    seed = {
        "youtube_id": vid,
        "url": "https://www.youtube.com/watch?v=" + vid,
        "title_en": meta.get("title"),
        "show": meta.get("channel") or meta.get("uploader"),
        "upload_date": meta.get("upload_date"),
        "duration_seconds": meta.get("duration"),
        "duration_hhmmss": hhmmss(meta.get("duration")),
        "captions_kind": kind,
        "chapters": chapters,
        "speakers": speaker_hints(meta),
        "description": (meta.get("description") or "")[:4000],
        "transcript_lines": len(lines),
    }
    seed_path = os.path.join(a.out_dir, "episode_seed.json")
    json.dump(seed, open(seed_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("✓ транскрипт : %s (%d строк, captions=%s)" % (txt_path, len(lines), kind))
    print("✓ метаданные : %s" % seed_path)
    print("  эпизод: %s — %s (%s)" % (seed["show"], seed["title_en"], seed["duration_hhmmss"]))
    print("  глав: %d · участники: host=%s guests=%s"
          % (len(chapters), seed["speakers"]["host_hint"], seed["speakers"]["guest_hints"]))


if __name__ == "__main__":
    main()
