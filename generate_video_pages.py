#!/usr/bin/env python3
"""Generate certification-series pages, general video watch pages, sitemap.xml,
and video-sitemap.xml from exam video.txt files plus general-video.xml.

Input line format:
    01_youtube_video.mp4 | 001_100297.png, 045_121187_A.png | https://www.youtube.com/watch?v=VIDEOID

No third-party Python packages are required.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "series.json"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
VIDEO_NS = "http://www.google.com/schemas/sitemap-video/1.1"
ET.register_namespace("", SITEMAP_NS)
ET.register_namespace("video", VIDEO_NS)


@dataclass
class Video:
    set_no: int
    source_name: str
    start_question: int
    end_question: int
    youtube_url: str
    youtube_id: str

    @property
    def count(self) -> int:
        return self.end_question - self.start_question + 1

    @property
    def embed_url(self) -> str:
        return f"https://www.youtube-nocookie.com/embed/{self.youtube_id}"

    @property
    def player_url(self) -> str:
        # Google accepts third-party iframe player URLs in video:player_loc.
        return f"https://www.youtube.com/embed/{self.youtube_id}"

    @property
    def thumbnail_url(self) -> str:
        # Stable YouTube thumbnail URL; hqdefault is broadly available.
        return f"https://i.ytimg.com/vi/{self.youtube_id}/hqdefault.jpg"


@dataclass
class GeneralVideo:
    title: str
    description: str
    youtube_url: str
    youtube_id: str
    category: str
    slug: str

    @property
    def embed_url(self) -> str:
        return f"https://www.youtube-nocookie.com/embed/{self.youtube_id}"

    @property
    def player_url(self) -> str:
        return f"https://www.youtube.com/embed/{self.youtube_id}"

    @property
    def thumbnail_url(self) -> str:
        return f"https://i.ytimg.com/vi/{self.youtube_id}/hqdefault.jpg"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_youtube_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().replace("www.", "")
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/embed/") or parsed.path.startswith("/shorts/"):
            parts = parsed.path.strip("/").split("/")
            video_id = parts[1] if len(parts) > 1 else ""
        else:
            video_id = ""
    else:
        video_id = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        raise ValueError(f"Could not parse YouTube video ID from: {url}")
    return video_id


def question_no(filename: str) -> int:
    name = Path(filename.strip()).name
    m = re.match(r"0*(\d+)_", name)
    if not m:
        m = re.search(r"(\d+)", name)
    if not m:
        raise ValueError(f"Could not parse question number from image name: {filename}")
    return int(m.group(1))


def parse_video_file(path: Path) -> list[Video]:
    videos: list[Video] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 3:
                raise ValueError(f"Bad line in {path}: {line}\nExpected 3 pipe-separated fields.")
            source, images, yt_url = parts
            img_parts = [x.strip() for x in images.split(",") if x.strip()]
            if len(img_parts) < 2:
                raise ValueError(f"Need first and last image names in: {line}")
            m = re.match(r"0*(\d+)", source)
            set_no = int(m.group(1)) if m else len(videos) + 1
            start_q = question_no(img_parts[0])
            end_q = question_no(img_parts[-1])
            if end_q < start_q:
                raise ValueError(f"Question range is reversed in: {line}")
            videos.append(Video(
                set_no=set_no,
                source_name=source,
                start_question=start_q,
                end_question=end_q,
                youtube_url=yt_url,
                youtube_id=extract_youtube_id(yt_url),
            ))
    videos.sort(key=lambda v: v.set_no)
    return videos


def slugify(text: str, max_len: int = 82) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) <= max_len:
        return text
    trimmed = text[:max_len].rsplit("-", 1)[0].strip("-")
    return trimmed or text[:max_len].strip("-")


def parse_general_video_file(path: Path) -> dict[str, list[GeneralVideo]]:
    """Read general-video.xml.

    Expected structure:
      <general-videos>
        <section slug="ai-machine-learning" title="AI &amp; Machine Learning Videos">
          <video>
            <title>...</title>
            <url>https://www.youtube.com/watch?v=...</url>
            <description>...</description>
          </video>
        </section>
      </general-videos>
    """
    allowed_sections = {"ai-machine-learning", "exam-study-guides"}
    sections: dict[str, list[GeneralVideo]] = {
        "ai-machine-learning": [],
        "exam-study-guides": [],
    }
    seen_slugs: set[str] = set()

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML in {path}: {exc}") from exc

    if root.tag != "general-videos":
        raise ValueError(f"Root element in {path} must be <general-videos>.")

    for section in root.findall("section"):
        category = (section.get("slug") or "").strip()
        if category not in allowed_sections:
            raise ValueError(
                f"Unsupported section slug '{category}' in {path}. "
                f"Allowed values: {', '.join(sorted(allowed_sections))}"
            )

        for node in section.findall("video"):
            title = (node.findtext("title") or "").strip()
            yt_url = (node.findtext("url") or "").strip()
            description = (node.findtext("description") or "").strip()

            missing = [
                name for name, value in (
                    ("title", title),
                    ("url", yt_url),
                    ("description", description),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"Video entry in section '{category}' is missing: {', '.join(missing)}"
                )

            if len(description) > 2048:
                raise ValueError(
                    f"Description exceeds 2048 characters for '{title}' in {path}."
                )

            slug_seed = title.split(":", 1)[0].strip() or title
            slug = slugify(slug_seed)
            base_slug = slug
            n = 2
            while slug in seen_slugs:
                slug = f"{base_slug}-{n}"
                n += 1
            seen_slugs.add(slug)

            sections[category].append(
                GeneralVideo(
                    title=title,
                    description=description,
                    youtube_url=yt_url,
                    youtube_id=extract_youtube_id(yt_url),
                    category=category,
                    slug=slug,
                )
            )

    return sections

def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def json_ld(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2).replace("</", "<\\/")


def page_head(title: str, description: str, canonical: str, ld: dict[str, Any], css_prefix: str) -> str:
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="canonical" href="{esc(canonical)}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{esc(canonical)}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="stylesheet" href="{css_prefix}styles.css">
  <script type="application/ld+json">
{json_ld(ld)}
  </script>
</head>'''


def nav(prefix: str) -> str:
    return f'''  <header class="topbar">
    <div class="container nav">
      <a class="brand" href="{prefix}">TechWith<span>Koushik</span></a>
      <nav class="navlinks" aria-label="Main navigation">
        <a href="{prefix}videos/ai-machine-learning/">AI &amp; Machine Learning</a>
        <a href="{prefix}cloud-certification-exam-guides.html">Exam Practice</a>
        <a href="{prefix}videos/exam-study-guides/">Study Guides</a>
        <a href="{prefix}youtube-resources.html">Resources</a>
      </nav>
    </div>
  </header>'''


def footer(prefix: str) -> str:
    return f'''  <footer class="footer">
    <div class="container">
      <strong>TechWithKoushik</strong>
      <p>Practical AI, cloud, certification and engineering resources by Koushik Maji.</p>
      <p><a href="https://youtube.com/@TechWithKoushikOfficial">YouTube</a> · <a href="{prefix}sitemap.xml">Sitemap</a> · <a href="{prefix}robots.txt">Robots</a></p>
      <p>© <span id="year"></span> koushikmaji.com</p>
    </div>
  </footer>
  <script src="{prefix}script.js"></script>'''


def make_video_title(series: dict[str, Any], v: Video) -> str:
    template = series.get("video_title_template", "{exam_code} Exam Questions & Answers 2026 — Set {set_no:02d}")
    return template.format(
        exam_code=series["exam_code"],
        exam_name=series["exam_name"],
        provider=series.get("provider", ""),
        set_no=v.set_no,
        start=v.start_question,
        end=v.end_question,
        count=v.count,
    )


def make_video_description(series: dict[str, Any], v: Video) -> str:
    template = series.get(
        "video_description_template",
        "Practice {exam_name} ({exam_code}) questions {start}–{end}. This independently created set contains {count} exam-preparation questions from TechWithKoushik.",
    )
    return template.format(
        exam_code=series["exam_code"],
        exam_name=series["exam_name"],
        provider=series.get("provider", ""),
        set_no=v.set_no,
        start=v.start_question,
        end=v.end_question,
        count=v.count,
    )


def render_series_index(site: dict[str, Any], series: dict[str, Any], videos: list[Video]) -> str:
    base = site["base_url"].rstrip("/")
    slug = series["slug"]
    canonical = f"{base}/videos/{slug}/"
    total = sum(v.count for v in videos)
    title = series.get("page_title") or f"{series['exam_code']} Practice Questions 2026 | TechWithKoushik"
    description = series.get("page_description") or (
        f"Practice {series['exam_name']} ({series['exam_code']}) questions and answers across {len(videos)} standalone sets from TechWithKoushik."
    )
    ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{series['exam_code']} Practice Questions 2026",
        "description": description,
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": site["site_name"], "url": base + "/"},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(videos),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "url": f"{base}/videos/{slug}/set-{v.set_no:02d}.html",
                    "name": make_video_title(series, v),
                }
                for i, v in enumerate(videos, 1)
            ],
        },
    }
    cards = []
    for v in videos:
        cards.append(f'''        <article class="video-card">
          <a class="video-thumb-link" href="set-{v.set_no:02d}.html" aria-label="Open Set {v.set_no:02d}">
            <img class="video-thumb" src="{esc(v.thumbnail_url)}" alt="{esc(make_video_title(series, v))}" loading="lazy">
            <span class="play-badge" aria-hidden="true">▶</span>
          </a>
          <div class="video-card-body">
            <span class="tag">SET {v.set_no:02d}</span>
            <h3><a href="set-{v.set_no:02d}.html">{esc(make_video_title(series, v))}</a></h3>
            <p><strong>Questions {v.start_question}–{v.end_question}</strong> · {v.count} questions</p>
            <div class="video-card-actions">
              <a class="text-link" href="set-{v.set_no:02d}.html">Open practice set →</a>
              <a class="text-link secondary-link" href="{esc(v.youtube_url)}" target="_blank" rel="noopener">YouTube ↗</a>
            </div>
          </div>
        </article>''')
    topics = ''.join(f'<span class="pill">{esc(x)}</span>' for x in series.get("topics", []))
    disclaimer = series.get("disclaimer", "These practice questions are independently created for educational and exam-preparation purposes and are not actual exam questions, dumps, leaked questions, or confidential certification content.")
    return f'''{page_head(title, description, canonical, ld, "../../")}
<body>
{nav("../../")}
  <main>
    <section class="container video-hero">
      <div class="crumb"><a href="../../">Home</a> / <a href="../../cloud-certification-exam-guides.html">Cloud Exam Guides</a> / {esc(series['exam_code'])}</div>
      <span class="badge">{esc(series['provider'])} · {esc(series['exam_name'])}</span>
      <h1>{esc(series['exam_code'])} Practice Questions &amp; Answers 2026</h1>
      <p class="lead">Test your knowledge with <strong>{total} independently created practice questions</strong> organized into <strong>{len(videos)} standalone sets</strong>. Start with any set—there is no required order.</p>
      <div class="btns">
        <a class="btn primary" href="#practice-sets">Start practicing</a>
        <a class="btn secondary" href="https://youtube.com/@TechWithKoushikOfficial" target="_blank" rel="noopener">Visit YouTube channel</a>
      </div>
      <div class="video-metrics" aria-label="Series summary">
        <div class="metric"><b>{total}</b><span>Practice questions</span></div>
        <div class="metric"><b>{len(videos)}</b><span>Standalone sets</span></div>
        <div class="metric"><b>{esc(series['exam_code'])}</b><span>Exam code</span></div>
        <div class="metric"><b>2026</b><span>Series</span></div>
      </div>
    </section>

    <section class="container section" id="practice-sets">
      <div class="section-heading">
        <div><span class="tag">{len(videos)} VIDEO SETS</span><h2>{esc(series['exam_code'])} practice sets</h2></div>
        <p class="section-note">Each set has its own dedicated watch page so the video is the main content of that page.</p>
      </div>
      <div class="video-grid">
{chr(10).join(cards)}
      </div>
    </section>

    <section class="container section">
      <div class="grid two">
        <article class="card">
          <h3>What this series covers</h3>
          <p>{topics or 'Exam-focused concepts and scenario practice.'}</p>
        </article>
        <article class="card">
          <h3>Exam-practice approach</h3>
          <p>{esc(disclaimer)}</p>
        </article>
      </div>
    </section>
  </main>
{footer("../../")}
</body>
</html>
'''


def render_watch_page(site: dict[str, Any], series: dict[str, Any], videos: list[Video], idx: int) -> str:
    v = videos[idx]
    base = site["base_url"].rstrip("/")
    slug = series["slug"]
    canonical = f"{base}/videos/{slug}/set-{v.set_no:02d}.html"
    video_title = make_video_title(series, v)
    description = make_video_description(series, v)
    title = f"{video_title} | TechWithKoushik"
    ld = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": video_title,
        "description": description,
        "thumbnailUrl": [v.thumbnail_url],
        "embedUrl": v.player_url,
        "url": canonical,
        "isPartOf": {
            "@type": "CollectionPage",
            "name": f"{series['exam_code']} Practice Questions 2026",
            "url": f"{base}/videos/{slug}/",
        },
    }
    prev_link = f'set-{videos[idx-1].set_no:02d}.html' if idx > 0 else None
    next_link = f'set-{videos[idx+1].set_no:02d}.html' if idx + 1 < len(videos) else None
    nav_buttons = []
    if prev_link:
        nav_buttons.append(f'<a class="btn secondary" href="{prev_link}">← Previous set</a>')
    nav_buttons.append('<a class="btn secondary" href="./">All sets</a>')
    if next_link:
        nav_buttons.append(f'<a class="btn primary" href="{next_link}">Next set →</a>')
    topics = ''.join(f'<span class="pill">{esc(x)}</span>' for x in series.get("topics", []))
    return f'''{page_head(title, description, canonical, ld, "../../")}
<body>
{nav("../../")}
  <main>
    <section class="container watch-hero">
      <div class="crumb"><a href="../../">Home</a> / <a href="./">{esc(series['exam_code'])}</a> / Set {v.set_no:02d}</div>
      <span class="badge">{esc(series['provider'])} · {esc(series['exam_name'])}</span>
      <h1>{esc(video_title)}</h1>
      <p class="lead">Questions <strong>{v.start_question}–{v.end_question}</strong> · <strong>{v.count} questions</strong>. Answer each question before the explanation, then review any weak areas.</p>
    </section>

    <section class="container watch-section">
      <div class="watch-player">
        <iframe
          src="{esc(v.embed_url)}"
          title="{esc(video_title)}"
          referrerpolicy="strict-origin-when-cross-origin"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowfullscreen></iframe>
      </div>
      <div class="watch-meta card">
        <div class="watch-meta-row">
          <div><span class="tag">SET {v.set_no:02d}</span><h2>Questions {v.start_question}–{v.end_question}</h2></div>
          <a class="btn secondary" href="{esc(v.youtube_url)}" target="_blank" rel="noopener">Watch on YouTube ↗</a>
        </div>
        <p>{esc(description)}</p>
        <p>{topics}</p>
      </div>
      <div class="watch-nav btns">
        {' '.join(nav_buttons)}
      </div>
    </section>

    <section class="container section">
      <div class="callout"><strong>Practice note:</strong> These questions are independently created for education and exam preparation. They are not actual certification exam questions or confidential exam content.</div>
    </section>
  </main>
{footer("../../")}
</body>
</html>
'''


def general_section_meta(category: str) -> dict[str, str]:
    if category == "ai-machine-learning":
        return {
            "label": "AI & Machine Learning",
            "title": "AI & Machine Learning Videos | TechWithKoushik",
            "h1": "AI & Machine Learning",
            "description": "Practical TechWithKoushik videos on AI, machine learning, generative AI, RAG, MCP, AI agents, security, engineering careers and modern AI systems.",
            "intro": "Explore practical explainers on AI, machine learning, generative AI, RAG, MCP, AI agents, security, engineering careers and the systems behind modern AI applications.",
        }
    return {
        "label": "Certification Study Guides",
        "title": "Certification Exam Study Guides | TechWithKoushik",
        "h1": "Certification Exam Study Guides",
        "description": "TechWithKoushik certification study-guide videos for cloud, AI, security and developer certification preparation.",
        "intro": "Use these focused study-guide videos to understand exam scope, preparation strategy, key concepts and revision priorities before certification exams.",
    }


def general_video_description(v: GeneralVideo) -> str:
    return v.description


def render_general_hub(site: dict[str, Any], category: str, videos: list[GeneralVideo]) -> str:
    base = site["base_url"].rstrip("/")
    meta = general_section_meta(category)
    canonical = f"{base}/videos/{category}/"
    ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": meta["h1"],
        "description": meta["description"],
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": site["site_name"], "url": base + "/"},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(videos),
            "itemListElement": [{
                "@type": "ListItem", "position": i,
                "url": f"{canonical}{v.slug}.html", "name": v.title
            } for i, v in enumerate(videos, 1)],
        },
    }
    cards = []
    for v in videos:
        cards.append(f'''        <article class="video-card">
          <a class="video-thumb-link" href="{esc(v.slug)}.html" aria-label="Open {esc(v.title)}">
            <img class="video-thumb" src="{esc(v.thumbnail_url)}" alt="{esc(v.title)}" loading="lazy">
            <span class="play-badge" aria-hidden="true">▶</span>
          </a>
          <div class="video-card-body">
            <span class="tag">{esc(meta["label"]).upper()}</span>
            <h3><a href="{esc(v.slug)}.html">{esc(v.title)}</a></h3>
            <div class="video-card-actions">
              <a class="text-link" href="{esc(v.slug)}.html">Watch on this site →</a>
              <a class="text-link secondary-link" href="{esc(v.youtube_url)}" target="_blank" rel="noopener">YouTube ↗</a>
            </div>
          </div>
        </article>''')
    return f'''{page_head(meta["title"], meta["description"], canonical, ld, "../../")}
<body>
{nav("../../")}
  <main>
    <section class="container video-hero">
      <div class="crumb"><a href="../../">Home</a> / {esc(meta["label"])}</div>
      <span class="badge">TechWithKoushik Video Library</span>
      <h1>{esc(meta["h1"])}</h1>
      <p class="lead">{esc(meta["intro"])}</p>
      <div class="video-metrics"><div class="metric"><b>{len(videos)}</b><span>Videos</span></div><div class="metric"><b>Free</b><span>Learning library</span></div></div>
    </section>
    <section class="container section" id="videos">
      <div class="section-heading"><div><span class="tag">{len(videos)} VIDEOS</span><h2>Browse the library</h2></div></div>
      <div class="video-grid">
{chr(10).join(cards)}
      </div>
    </section>
  </main>
{footer("../../")}
</body>
</html>
'''


def render_general_watch(site: dict[str, Any], category: str, videos: list[GeneralVideo], idx: int) -> str:
    v = videos[idx]
    base = site["base_url"].rstrip("/")
    meta = general_section_meta(category)
    canonical = f"{base}/videos/{category}/{v.slug}.html"
    description = general_video_description(v)
    title = f"{v.title} | TechWithKoushik"
    ld = {
        "@context": "https://schema.org", "@type": "VideoObject",
        "name": v.title, "description": description,
        "thumbnailUrl": [v.thumbnail_url], "embedUrl": v.player_url, "url": canonical,
        "isPartOf": {"@type": "CollectionPage", "name": meta["h1"], "url": f"{base}/videos/{category}/"},
    }
    buttons = []
    if idx > 0:
        buttons.append(f'<a class="btn secondary" href="{esc(videos[idx-1].slug)}.html">← Previous video</a>')
    buttons.append('<a class="btn secondary" href="./">All videos</a>')
    if idx + 1 < len(videos):
        buttons.append(f'<a class="btn primary" href="{esc(videos[idx+1].slug)}.html">Next video →</a>')
    return f'''{page_head(title, description, canonical, ld, "../../")}
<body>
{nav("../../")}
  <main>
    <section class="container watch-hero">
      <div class="crumb"><a href="../../">Home</a> / <a href="./">{esc(meta["label"])}</a></div>
      <span class="badge">{esc(meta["label"])}</span>
      <h1>{esc(v.title)}</h1>
      <p class="lead">Watch this TechWithKoushik video directly on the site or open it on YouTube.</p>
    </section>
    <section class="container watch-section">
      <div class="watch-player">
        <iframe src="{esc(v.embed_url)}" title="{esc(v.title)}" referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
      </div>
      <div class="watch-meta card">
        <div class="watch-meta-row"><div><span class="tag">{esc(meta["label"]).upper()}</span><h2>{esc(v.title)}</h2></div><a class="btn secondary" href="{esc(v.youtube_url)}" target="_blank" rel="noopener">Watch on YouTube ↗</a></div>
        <p>{esc(description)}</p>
      </div>
      <div class="watch-nav btns">{" ".join(buttons)}</div>
    </section>
  </main>
{footer("../../")}
</body>
</html>
'''


def write_sitemap(site: dict[str, Any], enabled_series: list[tuple[dict[str, Any], list[Video]]], general_sections: dict[str, list[GeneralVideo]] | None = None) -> None:
    base = site["base_url"].rstrip("/")
    root = ET.Element(ET.QName(SITEMAP_NS, "urlset"))

    def add_url(url: str, lastmod: str | None = None) -> None:
        u = ET.SubElement(root, ET.QName(SITEMAP_NS, "url"))
        ET.SubElement(u, ET.QName(SITEMAP_NS, "loc")).text = url
        if lastmod:
            ET.SubElement(u, ET.QName(SITEMAP_NS, "lastmod")).text = lastmod

    for item in site.get("static_urls", []):
        if isinstance(item, str):
            add_url(base + item)
        else:
            add_url(base + item["path"], item.get("lastmod"))

    today = date.today().isoformat()
    for s, videos in enabled_series:
        slug = s["slug"]
        add_url(f"{base}/videos/{slug}/", today)
        for v in videos:
            add_url(f"{base}/videos/{slug}/set-{v.set_no:02d}.html", today)

    for category, videos in (general_sections or {}).items():
        add_url(f"{base}/videos/{category}/", today)
        for v in videos:
            add_url(f"{base}/videos/{category}/{v.slug}.html", today)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(ROOT / "sitemap.xml", encoding="utf-8", xml_declaration=True)


def write_video_sitemap(site: dict[str, Any], enabled_series: list[tuple[dict[str, Any], list[Video]]], general_sections: dict[str, list[GeneralVideo]] | None = None) -> None:
    base = site["base_url"].rstrip("/")
    root = ET.Element(ET.QName(SITEMAP_NS, "urlset"))
    for s, videos in enabled_series:
        slug = s["slug"]
        for v in videos:
            u = ET.SubElement(root, ET.QName(SITEMAP_NS, "url"))
            watch_url = f"{base}/videos/{slug}/set-{v.set_no:02d}.html"
            ET.SubElement(u, ET.QName(SITEMAP_NS, "loc")).text = watch_url
            ve = ET.SubElement(u, ET.QName(VIDEO_NS, "video"))
            ET.SubElement(ve, ET.QName(VIDEO_NS, "thumbnail_loc")).text = v.thumbnail_url
            ET.SubElement(ve, ET.QName(VIDEO_NS, "title")).text = make_video_title(s, v)
            ET.SubElement(ve, ET.QName(VIDEO_NS, "description")).text = make_video_description(s, v)
            ET.SubElement(ve, ET.QName(VIDEO_NS, "player_loc")).text = v.player_url

    for category, videos in (general_sections or {}).items():
        for v in videos:
            u = ET.SubElement(root, ET.QName(SITEMAP_NS, "url"))
            watch_url = f"{base}/videos/{category}/{v.slug}.html"
            ET.SubElement(u, ET.QName(SITEMAP_NS, "loc")).text = watch_url
            ve = ET.SubElement(u, ET.QName(VIDEO_NS, "video"))
            ET.SubElement(ve, ET.QName(VIDEO_NS, "thumbnail_loc")).text = v.thumbnail_url
            ET.SubElement(ve, ET.QName(VIDEO_NS, "title")).text = v.title
            ET.SubElement(ve, ET.QName(VIDEO_NS, "description")).text = general_video_description(v)
            ET.SubElement(ve, ET.QName(VIDEO_NS, "player_loc")).text = v.player_url
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(ROOT / "video-sitemap.xml", encoding="utf-8", xml_declaration=True)


def validate_series_config(s: dict[str, Any]) -> None:
    required = ["slug", "exam_code", "exam_name", "provider", "video_file"]
    missing = [k for k in required if not s.get(k)]
    if missing:
        raise ValueError(f"Series config missing {missing}: {s}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", s["slug"]):
        raise ValueError(f"Invalid slug: {s['slug']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate TechWithKoushik exam-practice, AI/ML, study-guide pages and sitemaps.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--clean", action="store_true", help="Delete generated videos/<slug> directories before rebuilding.")
    args = parser.parse_args()

    cfg = read_json(args.config)
    site = cfg["site"]
    enabled: list[tuple[dict[str, Any], list[Video]]] = []

    for s in cfg.get("series", []):
        if not s.get("enabled", True):
            continue
        validate_series_config(s)
        src = (ROOT / s["video_file"]).resolve()
        if not src.exists():
            print(f"WARNING: skipping {s['exam_code']}: missing {src.relative_to(ROOT) if ROOT in src.parents else src}", file=sys.stderr)
            continue
        videos = parse_video_file(src)
        if not videos:
            print(f"WARNING: skipping {s['exam_code']}: no video rows", file=sys.stderr)
            continue
        out_dir = ROOT / "videos" / s["slug"]
        if args.clean and out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_series_index(site, s, videos), encoding="utf-8")
        for i, v in enumerate(videos):
            (out_dir / f"set-{v.set_no:02d}.html").write_text(render_watch_page(site, s, videos, i), encoding="utf-8")
        enabled.append((s, videos))
        total = sum(v.count for v in videos)
        print(f"Generated {s['exam_code']}: {len(videos)} sets, {total} questions -> videos/{s['slug']}/")

    general_sections: dict[str, list[GeneralVideo]] = {}
    general_file = ROOT / cfg.get("general_video_file", "general-video.xml")
    if general_file.exists():
        general_sections = parse_general_video_file(general_file)
        for category, videos in general_sections.items():
            if not videos:
                continue
            out_dir = ROOT / "videos" / category
            if args.clean and out_dir.exists():
                shutil.rmtree(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.html").write_text(render_general_hub(site, category, videos), encoding="utf-8")
            for i, v in enumerate(videos):
                (out_dir / f"{v.slug}.html").write_text(render_general_watch(site, category, videos, i), encoding="utf-8")
            print(f"Generated {general_section_meta(category)['label']}: {len(videos)} videos -> videos/{category}/")
    else:
        print(f"WARNING: general video file not found: {general_file}", file=sys.stderr)

    write_sitemap(site, enabled, general_sections)
    write_video_sitemap(site, enabled, general_sections)
    total_watch = sum(len(v) for _, v in enabled) + sum(len(v) for v in general_sections.values())
    print(f"Generated sitemap.xml and video-sitemap.xml for {total_watch} watch pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
