"""Validate the rendered review edition and package the standalone Medium handoff."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import hashlib
import json
import shutil
import zipfile
import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent


class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.refs=[];self.images=[];self.titles=[]
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        for key in ["href","src"]:
            if values.get(key):self.refs.append(values[key])
        if tag=="img":self.images.append(values)


def validate():
    site=ROOT/"_site"
    required=["index.html","worldwide.html","uk.html","children.html","justice.html","methods.html","medium/article.html"]
    for name in required:assert (site/name).is_file(),name
    broken=[];images=0
    for page in site.rglob("*.html"):
        parser=Links();parser.feed(page.read_text(encoding="utf-8"))
        for ref in parser.refs:
            u=urlsplit(ref)
            if u.scheme or u.netloc or not u.path or u.path.startswith("/"):continue
            target=(page.parent/unquote(u.path)).resolve()
            if not target.exists():broken.append((str(page.relative_to(site)),ref))
        for image in parser.images:
            if "assets/0" in image.get("src",""):
                assert image.get("alt"),image;images+=1
    assert not broken,broken[:20]
    who=pd.read_csv(ROOT/"data/who-non-partner-sexual-violence.csv")
    assert len(who)==138 and who.code.is_unique
    uk=who[who.code.eq("GBR")].iloc[0]
    assert round(uk.percent,1)==7.3 and round(uk.lower_95,1)==4.6 and round(uk.upper_95,1)==11.0
    trend=pd.read_csv(ROOT/"data/england-wales-survey-trend.csv")
    assert pd.isna(trend.loc[trend.year_ending_march.eq(2021),"percent"]).all()
    assert trend.year_ending_march.max()==2025
    recorded=pd.read_csv(ROOT/"data/unodc-recorded-rates.csv")
    assert not recorded.duplicated(["code","year","category"]).any()
    assert not recorded.code.eq("GBR").any(),"Do not invent an aggregate UK police series"
    medium=site/"medium/article.html"
    assert 'src="data:image/' in medium.read_text(encoding="utf-8"),"Medium preview must be standalone"
    soup=BeautifulSoup(medium.read_text(encoding="utf-8"),"html.parser")
    main=soup.find("main")
    assert main is not None
    styles="".join(str(style) for style in soup.head.find_all("style"))
    preview=('<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>Sexual violence in perspective — Medium edition</title>'+styles+
             '<style>body{background:#fcfcfa}main#quarto-document-content{max-width:780px;margin:54px auto;padding:0 24px;display:block}'
             'main p,main li{font-size:19px;line-height:1.8}main h1{font-size:43px}main img{max-width:100%;height:auto}'
             'main figcaption{font-size:14px}.quarto-title-meta{font-size:13px}@media(max-width:600px){main#quarto-document-content{margin:25px auto;padding:0 18px}main h1{font-size:34px}main p,main li{font-size:18px}}</style>'
             '</head><body>'+str(main)+'</body></html>')
    (ROOT/"medium/article.html").write_text(preview,encoding="utf-8")
    # Its local review link must also work after the standalone article is copied out of _site.
    p=ROOT/"medium/article.html";s=p.read_text(encoding="utf-8")
    if not json.loads((ROOT/"data/edition.json").read_text())["published_url"]:
        s=s.replace('href="../index.html"','href="../_site/index.html"')
        p.write_text(s,encoding="utf-8")
    with zipfile.ZipFile(ROOT/"medium-edition.zip","w",zipfile.ZIP_DEFLATED) as archive:
        for f in (ROOT/"medium").rglob("*"):
            if f.is_file():archive.write(f,f.relative_to(ROOT/"medium"))
    manifest={"review_edition":"2026-11-06","files":{
        p.relative_to(site).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in site.rglob("*") if p.is_file()}}
    (ROOT/"review-manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(f"PASS: {len(required)} pages; all relative file links; {images} chart references with alt text; 138 WHO countries; missing-year gap; unique UNODC records; standalone Medium HTML and ZIP.")


if __name__=="__main__":validate()
