#!/usr/bin/env python3
"""Fetch publishers' RSS/Atom headlines into a static, GitHub Pages-friendly JSON file.

Uses only Python's standard library. No tokens, proxies or paid services.
"""

from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'data' / 'news.json'
MAX_PER_SOURCE = 36
RETENTION_DAYS = 14
MAX_FEED_BYTES = 3_000_000

SOURCES = [
    {
        'id': 'verge', 'name': 'The Verge', 'website': 'https://www.theverge.com',
        'feeds': ['https://www.theverge.com/rss/index.xml'],
    },
    {
        'id': 'wired', 'name': 'WIRED', 'website': 'https://www.wired.com',
        'feeds': ['https://www.wired.com/feed/rss'],
    },
    {
        'id': 'mit', 'name': 'MIT Technology Review', 'website': 'https://www.technologyreview.com',
        'feeds': ['https://www.technologyreview.com/feed/', 'https://www.technologyreview.com/stories.rss'],
    },
    {
        'id': 'ars', 'name': 'Ars Technica', 'website': 'https://arstechnica.com',
        'feeds': ['https://feeds.arstechnica.com/arstechnica/index', 'https://arstechnica.com/feed/'],
    },
]

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.image = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'img' and not self.image:
            values = dict(attrs)
            self.image = values.get('src') or values.get('data-src') or values.get('data-original')
        if tag.lower() in ('p', 'div', 'br', 'li'):
            self.parts.append(' ')

    def handle_data(self, data):
        self.parts.append(data)


def compact(value):
    return re.sub(r'\s+', ' ', html.unescape(value or '')).strip()


def parse_html(raw):
    p = TextExtractor()
    try:
        p.feed(raw or '')
    except Exception:
        pass
    return compact(' '.join(p.parts)), p.image


def normal_url(value, base=''):
    value = compact(value)
    if not value:
        return ''
    value = urljoin(base, value)
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
            return ''
        return value[:2048]
    except ValueError:
        return ''


def date_to_iso(value):
    value = compact(value)
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def find_text(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text and found.text.strip():
            return found.text.strip()
    return ''


def image_from_entry(entry, base, html_image):
    # MediaRSS and RSS image enclosures are normally more reliable than embedded HTML.
    for node in entry.iter():
        tag = node.tag.rsplit('}', 1)[-1].lower()
        if tag in ('thumbnail', 'content', 'enclosure', 'image'):
            media_type = node.get('type', '')
            medium = node.get('medium', '')
            if tag == 'enclosure' and media_type and not media_type.startswith('image/'):
                continue
            if tag == 'content' and medium != 'image' and not media_type.startswith('image/'):
                continue
            url = normal_url(node.get('url', '') or node.get('href', ''), base)
            if not url and tag == 'image':
                url = normal_url(node.text or '', base)
            if url:
                return url
    return normal_url(html_image, base)


def extract_entry(entry, source, atom=False):
    ns = '{http://www.w3.org/2005/Atom}'
    if atom:
        title = find_text(entry, [ns + 'title', 'title'])
        link = ''
        for node in entry.findall(ns + 'link') + entry.findall('link'):
            if node.get('rel') in (None, 'alternate'):
                link = node.get('href', '')
                if link:
                    break
        if not link:
            link = find_text(entry, [ns + 'id'])
        raw_summary = find_text(entry, [ns + 'summary', ns + 'content', 'summary', 'content'])
        published = find_text(entry, [ns + 'published', ns + 'updated', 'published', 'updated'])
        cat = next((c.get('term', '') for c in entry.findall(ns + 'category')), '')
    else:
        title = find_text(entry, ['title'])
        link = find_text(entry, ['link']) or find_text(entry, ['guid'])
        raw_summary = find_text(entry, [
            'description', '{http://purl.org/rss/1.0/modules/content/}encoded',
            '{http://www.w3.org/2005/Atom}summary'
        ])
        published = find_text(entry, ['pubDate', '{http://purl.org/dc/elements/1.1/}date', 'published', 'date'])
        cat = find_text(entry, ['category'])

    link = normal_url(link, source['website'])
    plain_title, _ = parse_html(title)
    if not link or not plain_title:
        return None
    summary, img = parse_html(raw_summary)
    if summary.lower().startswith(plain_title.lower()):
        summary = compact(summary[len(plain_title):].lstrip(' .:–—'))
    if len(summary) > 215:
        summary = summary[:215].rsplit(' ', 1)[0].rstrip(' .,;:') + '…'
    image = image_from_entry(entry, source['website'], img)
    ident = hashlib.sha256((source['id'] + '|' + link).encode('utf-8')).hexdigest()[:20]
    return {
        'id': ident,
        'source': source['id'],
        'title': plain_title[:270],
        'url': link,
        'summary': summary,
        'image': image,
        'published_at': date_to_iso(published),
        'category': compact(cat)[:65],
    }


def parse_feed(data, source):
    root = ET.fromstring(data)
    kind = root.tag.rsplit('}', 1)[-1].lower()
    if kind == 'feed':
        entries = root.findall('{http://www.w3.org/2005/Atom}entry') or root.findall('entry')
        atom = True
    else:
        channel = root.find('channel')
        if channel is not None:
            entries = channel.findall('item')
        else:
            entries = root.findall('{http://purl.org/rss/1.0/}item')
        atom = False
    results, seen = [], set()
    for node in entries:
        item = extract_entry(node, source, atom)
        if not item or item['url'] in seen:
            continue
        seen.add(item['url'])
        results.append(item)
    results.sort(key=lambda x: x['published_at'] or '', reverse=True)
    return results[:MAX_PER_SOURCE]


def fetch(source):
    errors = []
    for url in source['feeds']:
        for attempt in range(2):
            try:
                headers = {
                    'User-Agent': 'TechBriefRSSWidget/1.0 (+GitHub Pages; RSS headlines only)',
                    'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5',
                }
                req = Request(url, headers=headers)
                with urlopen(req, timeout=22) as res:
                    data = res.read(MAX_FEED_BYTES + 1)
                if len(data) > MAX_FEED_BYTES:
                    raise ValueError('feed too large')
                items = parse_feed(data, source)
                if not items:
                    raise ValueError('feed returned no usable articles')
                return items, url
            except (URLError, HTTPError, TimeoutError, ValueError, ET.ParseError, OSError) as exc:
                message = f'{type(exc).__name__}: {str(exc)[:110]}'
                errors.append(message)
                if attempt == 0:
                    time.sleep(0.7)
    raise RuntimeError('; '.join(errors[-3:]))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def main():
    old = {}
    if OUTPUT.exists():
        try:
            old = json.loads(OUTPUT.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    old_articles = old.get('articles', [])
    old_sources = old.get('sources', {})
    if not isinstance(old_sources, dict):
        old_sources = {}
    by_source = {src['id']: [] for src in SOURCES}
    for article in old_articles if isinstance(old_articles, list) else []:
        if isinstance(article, dict) and article.get('source') in by_source:
            by_source[article['source']].append(article)

    statuses = {}
    for source in SOURCES:
        source_id = source['id']
        try:
            items, used_url = fetch(source)
            # Preserve articles recently seen in earlier snapshots. Some publishers
            # expose only 10 posts per RSS response; our widget can retain more.
            cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).timestamp()
            historical = []
            for old_item in by_source[source_id]:
                if not isinstance(old_item, dict) or not old_item.get('url') or not old_item.get('published_at'):
                    continue
                try:
                    published = datetime.fromisoformat(old_item['published_at'].replace('Z', '+00:00')).timestamp()
                except (ValueError, TypeError):
                    continue
                if published >= cutoff:
                    historical.append(old_item)
            combined_source = {item['url']: item for item in historical}
            combined_source.update({item['url']: item for item in items})
            by_source[source_id] = sorted(combined_source.values(), key=lambda x: x.get('published_at') or '', reverse=True)[:MAX_PER_SOURCE]
            statuses[source_id] = {
                'status': 'ok', 'count': len(by_source[source_id]), 'last_success_at': now_iso(),
                'feed_url': used_url, 'error': None,
            }
            print(f'OK  {source["name"]}: {len(items)} articles via {used_url}', flush=True)
        except RuntimeError as exc:
            cached = by_source[source_id][:MAX_PER_SOURCE]
            previous = old_sources.get(source_id, {})
            if not isinstance(previous, dict):
                previous = {}
            statuses[source_id] = {
                'status': 'stale' if cached else 'error',
                'count': len(cached),
                'last_success_at': previous.get('last_success_at'),
                'feed_url': previous.get('feed_url'),
                'error': str(exc)[:330],
            }
            print(f'WARN {source["name"]}: {exc} (retained {len(cached)} cached)', file=sys.stderr, flush=True)

    combined = []
    seen = set()
    for source in SOURCES:
        for item in by_source[source['id']][:MAX_PER_SOURCE]:
            if not isinstance(item, dict):
                continue
            link = item.get('url')
            if not link or link in seen:
                continue
            seen.add(link)
            combined.append(item)
    combined.sort(key=lambda item: item.get('published_at') or '', reverse=True)
    data = {
        'version': 1,
        'updated_at': now_iso(),
        'sources': statuses,
        'articles': combined,
    }
    OUTPUT.parent.mkdir(exist_ok=True, parents=True)
    new_text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    # Avoid pointless commits if the feed contents and source statuses didn't change.
    previous = old.copy()
    previous.pop('updated_at', None)
    compared = data.copy()
    compared.pop('updated_at', None)
    for bundle in (previous, compared):
        for stat in bundle.get('sources', {}).values():
            if isinstance(stat, dict):
                stat.pop('last_success_at', None)
    if previous != compared:
        OUTPUT.write_text(new_text, encoding='utf-8')
        print(f'Updated {OUTPUT.relative_to(ROOT)} with {len(combined)} articles.')
    else:
        print('No content changes; keeping previous snapshot.')

    if not combined:
        print('ERROR: No current or cached articles. Check RSS URLs and GitHub Actions logs.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
