# Sexual violence in perspective

A separate Quarto publication for GitHub Pages, with an accompanying Medium edition. Evidence snapshot: 6 November 2026. Adults and older adolescents are distinguished from retrospective childhood experiences; the source age bands overlap and must never be added together.

Run from this directory:

```powershell
python build_report.py
& "$env:LOCALAPPDATA\Programs\Quarto\bin\quarto.cmd" render .
python validate_report.py
```

`build_report.py` verifies the downloaded evidence hashes, prepares tidy CSVs, figures, offline country explorers and the Medium article. It does not fetch new data or alter the asylum publication. Dependencies: pandas, openpyxl, matplotlib and beautifulsoup4.

`sources/manifest.json` records original URLs, downloaded files and hashes, including failed attempts. The WHO and UNICEF PDF endpoints were inaccessible; WHO's own portal JSON and UNICEF's own press release provide the evidence actually used. The ONS CSV endpoint rate-limited an additional police trend request; the report uses the downloaded UNODC workbook and official bulletins instead. Missing values remain missing.

The published report is https://aloysius109.github.io/sexual-violence-report/ .

The rendered report is `_site/index.html`. The Medium handoff stays in `medium/article.html` and is not included in the website; its six PNGs in `medium/images/` are numbered 01–06 to match Figures 1–6, with instructions in `medium/PUBLISHING.txt`. Build with `python build_report.py --published-url https://aloysius109.github.io/sexual-violence-report/` to retain the public full-report link.

The reviewed `_site/` snapshot is copied to `docs/` with `python stage_publication.py`; file hashes are recorded in `docs/publication.json`. Run `python check_report.py` to check source hashes, report figures and data downloads. Run `python stage_publication.py --check` or `python check_publication.py` to validate the staged publication. The **Report checks** workflow runs the read-only report and publication checks on pushes and pull requests; the manual **Publish sexual violence report** workflow validates and deploys this report alone.

## Source watch

`python check_sources.py` re-checks every address in `sources/manifest.json` against what it serves today. Data files (CSV, JSON, spreadsheets) are compared by SHA-256, because a changed byte there is a changed figure. Web pages are checked for availability only: their markup churns for reasons unrelated to the statistics, so hashing them would raise a weekly false alarm. Requests are paced per host, because the ONS CSV generator rate-limits rapid requests. The sources that failed when this edition was archived are re-checked too, so a download that becomes available again is reported rather than forgotten. The script reads upstream only; it never writes data into the repository and never republishes.

The **Source watch** workflow runs the same check every Monday and opens an issue labelled `source-watch` when a data file changes, an archived source disappears, or a previously failed download starts working. Each distinct state is reported once: closing the issue dismisses that state, and a new state is added as a comment on the open issue. GitHub disables scheduled workflows after 60 days without repository activity; if this report sits untouched for two months, dispatch the workflow manually to re-enable it.

Adopting a change is a deliberate edit, not an automatic one: the prose figures are pinned by `check_report.py`, and `docs/` is hash-locked, so a refresh means re-running `build_report.py`, re-rendering, re-validating, restaging and republishing. The current archive status, including sources that remain blocked or are only intermittently reachable, is documented in `methods.qmd` under “Coverage and access limitations.”

## Analytics

The report uses GoatCounter, configured in `analytics.html`. Update the `data-goatcounter` URL in that partial if the account changes. It is used without cookies, a consent banner or personal-data collection.
