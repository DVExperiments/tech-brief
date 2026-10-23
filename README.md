# TECH BRIEF — embeddable technology news widget

A polished, small-screen-friendly Google Sites news widget hosted entirely on GitHub Pages. It gathers recent headlines from **The Verge, WIRED, MIT Technology Review, and Ars Technica**, lets visitors switch publishers in the left sidebar, search titles/topics, choose a time range, and open articles on the publishers' own sites.

**No paid APIs, tokens, databases, servers, or external JavaScript libraries required.** GitHub Actions regularly fetches RSS/Atom and saves a small JSON file. The frontend reads that local JSON file, avoiding browser cross-origin restrictions on publisher RSS feeds.

The article list scrolls **inside** the embedded page, so an embed with a fixed height can still show many headlines. On narrow widths the sidebar becomes a horizontal publisher strip.

## Updates and expected behavior

- GitHub Actions checks feeds at **:17 and :47 every hour** (UTC cron). GitHub Actions scheduled runs can sometimes be delayed or skipped; these are **not guaranteed real-time updates**.
- `data/news.json` changes only when article content/source statuses change, reducing unnecessary commits. The updated-at time indicates when the displayed snapshot changed, **not** necessarily when RSS was last checked.
- Clicking **Refresh** in the widget re-downloads the currently published snapshot; it **does not trigger** a GitHub Actions workflow.
- If a single source fails, the collector retains that source's previous articles and shows a small warning. If all sources fail and there is no cached data, the workflow exits unsuccessfully and keeps the previous JSON.
- Images are loaded from the publishers' RSS-provided URLs when available. Some sites block hotlinking or omit images; the widget automatically shows attractive publisher-specific placeholders.
- GitHub may disable scheduled workflows after **60 days of inactivity** on a public repo. Re-enable the workflow if that occurs.
- RSS feeds often expose only 10–50 posts at a time. The collector retains previously seen stories for up to **14 days** (maximum 36 per source). This is for recent discovery, **not** a complete searchable archive.

## Customize

- **Site name, hero text, article page size:** `config.js`
- **Colors, layout, fonts and Google Sites embed responsiveness:** `assets/styles.css`
- **Publishers, RSS URLs, collection size:** `scripts/update_feeds.py`. Source changes also require matching labels/classes in `index.html` and `assets/app.js`.
- **Automation schedule:** `.github/workflows/update-news.yml` (cron syntax in UTC)

The source buttons, article summaries, and images are generated from RSS feed metadata. Articles open in new tabs on the original publisher sites. Some sites may require subscriptions for the full article; the widget does not bypass paywalls.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Widget says no articles yet | Run **Actions → Update tech news → Run workflow** and make sure it commits `data/news.json`. |
| The Action reports 403 / 429 or a feed error | Check its log. Some providers rate-limit automated requests. Try the workflow later or use the feed fallback; cached articles are retained. |
| Action succeeds but can't push | Review **Settings → Actions → General → Workflow permissions**, and branch protection rules. |
| GitHub Pages shows README or 404 | Ensure `index.html` is at the **repository root** and Pages uses the correct branch/root. |
| Google Sites embed is cramped | Set the embed height to ~800 px and widen the section. On narrow embeds, the source selector becomes a horizontal strip. |
| Images are missing | The publisher may not supply images or may block cross-site loading. Publisher fallback covers appear by design. |
| Data does not look fresh | Look at the Actions tab, the feed's actual publish frequency, and the time of the last changed snapshot. |
| Testing by opening `index.html` with a `file://` URL | Local browsers block `fetch()` for local files. Use `python -m http.server 8000` in the project folder, then open `http://localhost:8000/`. |

## Project files

```text
index.html                   # Website/iframe entry point
config.js                    # Easy title and appearance labels
assets/styles.css           # Responsive layout and theme
assets/app.js               # Source selection, search, cards, pagination
assets/favicon.svg          # Icon
scripts/update_feeds.py     # Python RSS collector (standard library)
data/news.json              # Generated news snapshot
.github/workflows/update-news.yml  # Scheduled GitHub Action
.nojekyll                   # Preserve GitHub Pages file paths
```

All story metadata is credited to its original publisher and links to its original article. This project is intended as a headline discovery widget, not a full-article mirror.
