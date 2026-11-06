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

The rendered report is `_site/index.html`. The Medium handoff is `medium/article.html`, with six PNGs in `medium/images/` and instructions in `medium/PUBLISHING.txt`. Build with `python build_report.py --published-url https://aloysius109.github.io/sexual-violence-report/` to retain the public full-report link.

The reviewed `_site/` snapshot is copied to `docs/`, with file hashes in `docs/publication.json`. Run `python check_publication.py` before publication. The manual **Publish sexual violence report** workflow validates and deploys this report alone.
