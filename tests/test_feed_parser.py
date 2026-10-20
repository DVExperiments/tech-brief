"""Offline parser tests, runnable with python -m unittest discover -s tests."""
import importlib.util
from pathlib import Path
import unittest

file_path = Path(__file__).parents[1] / 'scripts' / 'update_feeds.py'
spec = importlib.util.spec_from_file_location('update_feeds', file_path)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
SOURCE = collector.SOURCES[0]

class FeedParserTests(unittest.TestCase):
    def test_rss_images_dates_and_escaping(self):
        xml = b'''<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/" version="2.0"><channel>
        <item><title>AI &amp; Us</title><link>https://example.org/test</link>
        <pubDate>Tue, 20 Oct 2026 12:10:00 GMT</pubDate><category>Tech</category>
        <description><![CDATA[<p>Summary <b>text</b> of article.</p><img src="https://cdn.example.org/backup.jpg">]]></description>
        <media:content url="https://cdn.example.org/hero.jpg" medium="image" />
        </item></channel></rss>'''
        articles = collector.parse_feed(xml, SOURCE)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['title'], 'AI & Us')
        self.assertEqual(articles[0]['summary'], 'Summary text of article.')
        self.assertEqual(articles[0]['image'], 'https://cdn.example.org/hero.jpg')
        self.assertEqual(articles[0]['published_at'], '2026-10-20T12:10:00Z')

    def test_atom_and_malicious_link(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>Latest</title><link href="https://example.org/news" rel="alternate"/>
          <updated>2026-10-19T10:12:00Z</updated><summary>Atom summary</summary>
          </entry><entry><title>Unsafe</title><link href="javascript:alert(1)"/></entry></feed>'''
        articles = collector.parse_feed(xml, SOURCE)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['url'], 'https://example.org/news')
        self.assertEqual(articles[0]['summary'], 'Atom summary')
        self.assertEqual(articles[0]['published_at'], '2026-10-19T10:12:00Z')

    def test_deduplicate_rss(self):
        xml = b'<rss><channel><item><title>A</title><link>https://example.org/a</link></item><item><title>A</title><link>https://example.org/a</link></item></channel></rss>'
        self.assertEqual(len(collector.parse_feed(xml, SOURCE)), 1)

    def test_dates_and_url_validation(self):
        self.assertIsNone(collector.date_to_iso('not-a-date'))
        self.assertEqual(collector.normal_url('javascript:alert(1)'), '')
        self.assertEqual(collector.normal_url('https://evil:pass@example.org/private'), '')

if __name__ == '__main__': unittest.main()
