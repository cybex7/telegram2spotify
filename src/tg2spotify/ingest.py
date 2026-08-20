"""Stage 1 — read the Telegram export into SQLite, five metadata sources per track.

Sources are stored side by side, never collapsed, so later stages can weigh
them: Telegram's performer, Telegram's title, the message caption, the
filename, and the file's own ID3 tags.
"""

import csv
import json
import os
from typing import Any, Dict, List, Optional

from . import db, id3
from .clean import build_hypotheses, clean_field

EXCLUDE_REASONS = {
    "voice_message": "voice message (<=45s, no title/performer)",
    "video_file": "video file (skipped by decision)",
    "sticker": "sticker",
    "animation": "animation",
}
OVERSIZE_MARKER = "File exceeds maximum size"


def _caption(msg: Dict[str, Any]) -> str:
    """Flatten Telegram's text/text_entities into one string."""
    txt = msg.get("text")
    if isinstance(txt, str):
        return txt
    parts: List[str] = []
    for part in (txt or []):
        parts.append(part if isinstance(part, str) else str(part.get("text", "")))
    return " ".join(p for p in parts if p).strip()


def ingest(export_dir: str, db_path: str, report_dir: str) -> Dict[str, int]:
    with open(os.path.join(export_dir, "result.json"), encoding="utf-8") as fh:
        messages = json.load(fh)["messages"]

    con = db.connect(db_path)
    files_dir = os.path.join(export_dir, "files")
    stats = {"audio": 0, "excluded": 0, "id3_hits": 0, "missing_file": 0, "hypotheses": 0}

    for msg in messages:
        mtype = msg.get("media_type")
        mid = msg.get("id")
        if mtype != "audio_file":
            if mtype in EXCLUDE_REASONS:
                con.execute("INSERT OR REPLACE INTO excluded VALUES (?,?,?)",
                            (mid, mtype, EXCLUDE_REASONS[mtype]))
                stats["excluded"] += 1
            continue

        rel = msg.get("file") or ""
        oversize = OVERSIZE_MARKER in rel
        abs_path = os.path.join(export_dir, rel) if rel and not oversize else ""
        present = bool(abs_path) and os.path.isfile(abs_path)
        if not present:
            stats["missing_file"] += 1

        tags = id3.read_tags(abs_path) if present and rel.lower().endswith(".mp3") else {}
        if tags.get("artist") or tags.get("title"):
            stats["id3_hits"] += 1

        performer, title = msg.get("performer"), msg.get("title")
        caption = _caption(msg)
        basename = os.path.basename(rel)

        hyps = build_hypotheses(
            performer=performer, title=title, filename=basename, caption=caption,
            id3_artist=tags.get("artist"), id3_title=tags.get("title"))

        top = hyps[0] if hyps else None
        rules = sorted(set(
            clean_field(performer).rules + clean_field(title).rules
            + clean_field(basename).rules))

        length_ms = tags.get("length")
        con.execute("""INSERT OR REPLACE INTO tracks
            (msg_id,date,file,file_present,mime,duration_tg,tg_performer,tg_title,caption,
             id3_artist,id3_title,id3_length_ms,clean_artist,clean_title,rules,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mid, msg.get("date"), rel, int(present), msg.get("mime_type"),
             msg.get("duration_seconds"), performer, title, caption,
             tags.get("artist"), tags.get("title"),
             int(length_ms) if (length_ms or "").isdigit() else None,
             top.artist if top else None, top.title if top else None,
             ",".join(rules),
             "ingested" if hyps else "no_metadata"))

        con.execute("DELETE FROM hypotheses WHERE msg_id=?", (mid,))
        for rank, h in enumerate(hyps):
            con.execute("INSERT INTO hypotheses VALUES (?,?,?,?,?,?,0)",
                        (mid, rank, h.artist, h.title, h.source, h.confidence))
        if oversize:
            con.execute("INSERT OR REPLACE INTO excluded VALUES (?,?,?)",
                        (mid, "oversize", "Telegram refused to export: " + rel))
        stats["audio"] += 1
        stats["hypotheses"] += len(hyps)

    con.commit()
    _write_report(con, report_dir)
    return stats


def _write_report(con, report_dir: str) -> None:
    """Human-auditable CSV: what came in, what came out, and why."""
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, "cleaned.csv")
    rows = con.execute("SELECT * FROM tracks ORDER BY msg_id").fetchall()
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["msg_id", "tg_performer", "tg_title", "filename",
                    "id3_artist", "id3_title", "clean_artist", "clean_title",
                    "rules_fired", "duration_s", "n_hyp", "hypotheses"])
        for r in rows:
            hyps = con.execute(
                "SELECT artist,title,source FROM hypotheses WHERE msg_id=? ORDER BY rank",
                (r["msg_id"],)).fetchall()
            w.writerow([
                r["msg_id"], r["tg_performer"], r["tg_title"],
                os.path.basename(r["file"] or ""), r["id3_artist"], r["id3_title"],
                r["clean_artist"], r["clean_title"], r["rules"], r["duration_tg"],
                len(hyps),
                " | ".join(f"{h['artist']} :: {h['title']} [{h['source']}]" for h in hyps),
            ])
