"""Rebuild the frozen evidence edition offline; never refresh or publish implicitly."""
from pathlib import Path
import argparse
import csv
import hashlib
import html
import io
import json
import re
import shutil
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
DATA = ROOT / "data"
ASSETS = ROOT / "assets"
TEAL, INK, GOLD = "#267c80", "#263e4c", "#b58a59"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.spines.left": False, "axes.edgecolor": "#cbd5da",
                     "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK,
                     "ytick.color": INK, "figure.facecolor": "white", "axes.facecolor": "white"})


def verify_sources():
    manifest = json.loads((SOURCES / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["sources"]:
        if "file" not in item:
            continue
        path = ROOT / item["file"]
        assert path.resolve().is_relative_to(ROOT), item["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], path
    return manifest


def ons_rows(name):
    return list(csv.reader(io.StringIO((SOURCES / name).read_bytes().decode("utf-8", errors="replace"))))


def savefig(fig, name, title, subtitle, footer):
    fig.suptitle(title, x=.025, y=.985, ha="left", fontsize=17, fontweight="bold", color=INK)
    fig.text(.025, .925, subtitle, ha="left", va="top", fontsize=10, color="#576a75")
    fig.text(.025, .025, footer, ha="left", va="bottom", fontsize=9, color="#576a75")
    fig.tight_layout(rect=(.015, .09, .99, .86))
    fig.savefig(ASSETS / name, dpi=180, bbox_inches="tight")
    plt.close(fig)


def bars(labels, values, filename, title, subtitle, footer, xmax=None):
    fig, ax = plt.subplots(figsize=(11, max(4.8, len(labels)*.42+2.1)))
    pos = np.arange(len(labels))
    ax.barh(pos, values, color=TEAL, height=.55)
    ax.set_yticks(pos, labels)
    ax.invert_yaxis()
    limit = xmax or max(values)*1.22
    ax.set_xlim(0, limit)
    ax.set_xlabel("Percentage (%)")
    ax.grid(axis="x", alpha=.15)
    ax.set_axisbelow(True)
    for y, value in zip(pos, values):
        ax.text(value+limit*.015, y, f"{value:.1f}%", va="center", fontsize=11)
    savefig(fig, filename, title, subtitle, footer)


def table_html(frame, fields, headers, ident, controls="", attrs=None):
    rows = []
    for _, row in frame.iterrows():
        extra = attrs(row) if attrs else ""
        cls = ' class="uk-row"' if str(row.get("code", "")).startswith("GBR") else ""
        cells = "".join("<td>"+html.escape(str(row[f]))+"</td>" for f in fields)
        rows.append(f"<tr{cls} {extra}>{cells}</tr>")
    return (f'<section data-explorer id="{ident}"><div class="explorer-tools">'
            f'<label>Search <input type="search" aria-label="Search {ident}" placeholder="Country or area"></label>'
            + controls + '<output aria-live="polite"></output></div><div class="table-scroll"><table><thead><tr>'
            + "".join("<th scope=\"col\">"+h+"</th>" for h in headers)
            + "</tr></thead><tbody>"+"".join(rows)+"</tbody></table></div></section>")


def prepare_who():
    raw = json.loads((SOURCES / "who-npsv-countries.json").read_text(encoding="utf-8"))
    rows = []
    for country in raw["countries"]:
        age = [e for e in country["estimates"] if e["code"] == "15_99"]
        if not age:
            continue
        v = age[0]["values"]
        if not all(k in v for k in ["lifetime", "lci_lifetime", "uci_lifetime"]):
            continue
        mean, low, high = [float(v[k])*100 for k in ["lifetime", "lci_lifetime", "uci_lifetime"]]
        assert 0 <= low <= mean <= high <= 100
        rows.append({"code":country["code"], "country":country["name"], "percent":mean,
                     "lower_95":low, "upper_95":high, "estimate_year":2023,
                     "population":"Women aged 15+", "reference_period":"Since age 15",
                     "measure":"Non-partner sexual violence", "source":"WHO VAW portal"})
    df = pd.DataFrame(rows).sort_values("country")
    assert len(df) == 138 and not df.code.duplicated().any()
    df.to_csv(DATA / "who-non-partner-sexual-violence.csv", index=False)
    locations=json.loads((SOURCES/"who-locations.json").read_text(encoding="utf-8"))
    pd.DataFrame([{"code":c["code"],"country":c["name"],
                   "requested":c["status"]==1,"returned":c["code"] in set(df.code)}
                  for c in locations["countries"]]).to_csv(DATA/"who-coverage.csv",index=False)
    # Preserve the country-specific study dates: an estimate-year is not a survey-year.
    pd.json_normalize(raw["sources"]).to_csv(DATA / "who-underlying-studies.csv", index=False)
    display = df.copy()
    for c in ["percent", "lower_95", "upper_95"]:
        display[c] = display[c].map(lambda n:f"{n:.1f}%")
    (ROOT / "_who-explorer.html").write_text(table_html(display,
        ["country", "percent", "lower_95", "upper_95"],
        ["Country / area", "Estimate", "95% lower", "95% upper"], "who-countries"), encoding="utf-8")
    selected = ["AUS", "BRA", "FRA", "DEU", "IND", "JPN", "NZL", "ZAF", "SWE", "GBR", "USA"]
    peer = df[df.code.isin(selected)].sort_values("country")
    fig, ax = plt.subplots(figsize=(11, 7.7))
    for y, (_, r) in enumerate(peer.iterrows()):
        color = GOLD if r.code == "GBR" else TEAL
        ax.errorbar(r.percent, y, xerr=[[r.percent-r.lower_95], [r.upper_95-r.percent]],
                    fmt="o", color=color, capsize=4, markersize=7, linewidth=2)
    ax.set_yticks(range(len(peer)), peer.country)
    ax.invert_yaxis(); ax.set_xlim(0, 52); ax.set_xlabel("Percentage (%)"); ax.grid(axis="x", alpha=.15)
    savefig(fig, "01-who-comparison.png", "One measure, different national estimates",
            "Non-partner sexual violence since age 15 · Women aged 15+ · WHO 2023 estimates",
            "Dots: estimates. Lines: 95% uncertainty intervals. Selected examples in alphabetical order.\nNot all sexual assault; excludes partner violence. Source: WHO VAW portal, accessed 6 Nov 2026.")
    return df


def prepare_unodc():
    raw = pd.read_excel(SOURCES / "unodc-violent-sexual-2026.xlsx", header=2)
    keep = ((raw.Indicator == "Violent offences") & (raw.Dimension == "by type of offence")
            & (raw.Sex == "Total") & (raw.Age == "Total")
            & (raw["Unit of measurement"] == "Rate per 100,000 population")
            & raw.Category.isin(["Sexual violence", "Sexual violence: Rape", "Sexual violence: Sexual assault"]))
    df = raw[keep].rename(columns={"Iso3_code":"code", "Country":"country", "Year":"year",
                                  "Category":"category", "VALUE":"rate"})
    df = df[["code", "country", "year", "category", "rate"]].sort_values(["country","year","category"])
    assert not df.duplicated(["code","year","category"]).any()
    assert df.rate.notna().all() and (df.rate >= 0).all()
    df.to_csv(DATA / "unodc-recorded-rates.csv", index=False)
    display = df.copy();display["rate"] = display.rate.map(lambda n:f"{n:.2f}")
    display["year"] = display.year.astype(int)
    control = '<label>Year <select aria-label="Year" data-field="year"><option value="">All years</option>'
    control += "".join(f'<option value="{y}"{ " selected" if y==2022 else ""}>{y}</option>' for y in sorted(df.year.unique(), reverse=True)) + '</select></label>'
    control += '<label>Offence <select aria-label="Offence" data-field="category"><option value="">All categories</option>'
    control += "".join(f'<option value="{html.escape(c)}"{ " selected" if c=="Sexual violence: Rape" else ""}>{html.escape(c)}</option>' for c in sorted(df.category.unique())) + '</select></label>'
    (ROOT / "_unodc-explorer.html").write_text(table_html(display,
        ["country","year","category","rate"], ["Country / jurisdiction","Year","Recorded category","Per 100,000"],
        "recorded-offences", control, lambda r:f'data-year="{r.year}" data-category="{html.escape(r.category)}"'), encoding="utf-8")
    # Common year deliberately selected because the E&W return ends at 2022.
    selected = ["AUS","BRA","FRA","DEU","IND","JPN","NZL","ZAF","SWE","USA","GBR_E_W","GBR_NI","GBR_S"]
    peers = df[(df.year==2022)&(df.category=="Sexual violence: Rape")&df.code.isin(selected)].sort_values("country")
    peers.to_csv(DATA / "unodc-2022-comparison.csv", index=False)
    fig, ax = plt.subplots(figsize=(11, 7.6))
    ax.barh(range(len(peers)), peers.rate, color=[GOLD if c.startswith("GBR") else TEAL for c in peers.code])
    labels = peers.country.str.replace("United Kingdom (", "", regex=False).str.replace(")", "", regex=False)
    ax.set_yticks(range(len(peers)), labels);ax.invert_yaxis();ax.set_xlabel("Recorded rape offences per 100,000 population")
    ax.grid(axis="x",alpha=.15);ax.set_axisbelow(True)
    savefig(fig,"02-recorded-comparison.png","Police records describe recorded demand",
            "UNODC · Rape offences recorded in 2022 · All sexes and ages · Alphabetical examples",
            "Definitions, recording and disclosure differ. These are offences, not survey prevalence or a safety ranking.\nUK jurisdictions remain separate. Missing countries are omitted. Source: UNODC CTS snapshot, 28 Sep 2026.")
    return df


def prepare_uk():
    rows = ons_rows("ons-trend-2025.csv")
    points = []
    for r in rows:
        if r and re.fullmatch(r"Mar \d{4}", r[0].strip()) and len(r)>1:
            try: value=float(r[1])
            except ValueError: value=None
            points.append({"year_ending_march":int(r[0][-4:]), "percent":value})
    trend = pd.DataFrame(points)
    # Keep the survey suspension as a gap even if the source omits the row entirely.
    trend = trend.set_index("year_ending_march").reindex(range(2005,2026)).rename_axis("year_ending_march").reset_index()
    trend.to_csv(DATA / "england-wales-survey-trend.csv",index=False)
    assert trend.loc[trend.year_ending_march==2025,"percent"].iloc[0]==2.4
    fig, ax = plt.subplots(figsize=(11,5.7));ax.plot(trend.year_ending_march,trend.percent,color=TEAL,marker="o",markersize=4,linewidth=2)
    ax.set_ylim(0,4);ax.set_xlim(2004.5,2025.5);ax.set_xticks([2005,2010,2015,2020,2025]);ax.set_ylabel("Percentage (%)");ax.set_xlabel("Year ending March");ax.grid(axis="y",alpha=.15)
    savefig(fig,"03-england-wales-trend.png","A survey trend with an explicit stopping point",
            "Sexual assault including attempts in the last year · Ages 16–59 · England and Wales",
            "No 2021 estimate. 2022–2025 have source quality cautions; 2024–2025 use a half sample.\nThe redesigned 2026 sexual-victimisation measure is NOT joined to this line. Source: ONS, YE March 2025.")
    age_rows = ons_rows("ons-victims-2025-figure-3.csv")
    ages = [{"age_group":r[0],"percent":float(r[1])} for r in age_rows if r and re.match(r"\d+ (to|years)",r[0])]
    age = pd.DataFrame(ages);assert len(age)==8
    age.to_csv(DATA / "england-wales-age-2025.csv",index=False)
    bars(age.age_group,age.percent,"04-england-wales-age.png","Young people report higher prevalence",
         "Sexual assault including attempts in the last year · England and Wales · YE March 2025",
         "People aged 16+ in private households. Half-sample estimates; sampling uncertainty applies.\n16–17-year-olds are included in this source. Source: ONS victim characteristics, Figure 3.",8)
    latest = pd.DataFrame({"population":["All people aged 16+","Women aged 16+","Men aged 16+"],"percent":[2.1,2.8,1.4]})
    latest.to_csv(DATA / "england-wales-sexual-victimisation-2026.csv",index=False)
    bars(latest.population,latest.percent,"05-latest-survey.png","The latest measure begins a new series",
         "Sexual victimisation including attempts, last year · England and Wales · YE March 2026",
         "Broader redesigned measure: includes image-related experiences and being forced to penetrate.\nNot comparable with earlier sexual-assault estimates. Source: ONS crime bulletin, YE June 2026.",4)


def prepare_children():
    # Published UNICEF regional estimates; these are lifetime experiences among girls/women alive in 2024.
    regions = ["Sub-Saharan Africa","Eastern & South-Eastern Asia","Central & Southern Asia","Europe & Northern America","Latin America & Caribbean","Northern Africa & Western Asia","Oceania"]
    percent = [22,8,9,14,18,15,34];millions=[79,75,73,68,45,29,6]
    df=pd.DataFrame({"region":regions,"percent":percent,"survivors_millions":millions,"publication_year":2024})
    df.to_csv(DATA / "unicef-childhood-regions.csv",index=False)
    bars(regions,percent,"06-childhood-worldwide.png","Childhood sexual violence crosses every region",
         "Girls and women who experienced rape or sexual assault before age 18 · UNICEF 2024 estimates",
         "Lifetime experiences among girls/women alive at estimation; NOT an annual rate among current children.\nRegional point estimates; underlying data coverage and quality vary. Source: UNICEF, 10 Oct 2024.",42)
    rows=ons_rows("ons-childhood-2024-figure-1.csv")
    r=next(r for r in rows if r and r[0]=="Sexual abuse")
    child=pd.DataFrame({"population":["All adults aged 18+","Women aged 18+","Men aged 18+"],"percent":[float(r[3]),float(r[2]),float(r[1])]})
    child.to_csv(DATA / "england-wales-childhood-2024.csv",index=False)
    bars(child.population,child.percent,"07-childhood-england-wales.png","Adults recalling sexual abuse before age 18",
         "England and Wales · CSEW YE March 2024 · Retrospective childhood experiences",
         "Includes non-contact abuse, contact abuse and rape/penetration including attempts.\nNot current child prevalence; not comparable with the former pre-16 series. Source: ONS, 5 Nov 2025.",18)


def prepare_justice():
    d=pd.DataFrame({"recorded_cohort":["YE March 2025","YE March 2025","YE March 2026"],
                    "snapshot":["First published July 2025","Updated July 2026","First published July 2026"],"charge_summons_percent":[2.8,5.2,3.4]})
    d.to_csv(DATA / "rape-outcome-maturity.csv",index=False)
    bars(["2025 cohort: first release","2025 cohort: later update","2026 cohort: first release"],
         d.charge_summons_percent,"08-outcome-maturity.png","An early outcome rate is not a final result",
         "Recorded rape offences assigned a charge/summons outcome · England and Wales",
         "The same 2025 recording cohort rises from 2.8% to 5.2% as investigations mature.\nA charge is not a conviction. Source: Home Office Crime outcomes 2025–2026, section 2.4.",7)
    ni=pd.read_excel(SOURCES/"psni-march-2026.xlsx",sheet_name="Table 1",header=None)
    row=ni[ni[0].eq("SEXUAL OFFENCES")].iloc[0];assert int(row[2])==4459
    pd.DataFrame([
        {"jurisdiction":"England and Wales","period":"YE June 2026","recorded_sexual_offences":218994,"source":"ONS October 2026 crime bulletin"},
        {"jurisdiction":"Scotland","period":"2025–26","recorded_sexual_offences":16430,"source":"Scottish Government June 2026 bulletin"},
        {"jurisdiction":"Northern Ireland","period":"2025–26","recorded_sexual_offences":int(row[2]),"source":"PSNI May 2026, Table 1"},
    ]).to_csv(DATA/"uk-jurisdiction-snapshots.csv",index=False)


def medium(published_url):
    target=ROOT/"medium";images=target/"images";images.mkdir(parents=True,exist_ok=True)
    source=(ROOT/"medium-article.qmd").read_text(encoding="utf-8")
    if published_url:
        assert published_url.startswith("https://") and " " not in published_url
        source=source.replace("FULL_REPORT_LINK",published_url.rstrip("/")+"/")
    else:
        source=source.replace("FULL_REPORT_LINK","../index.html")
    for name in re.findall(r"assets/([^\s)]+\.png)",source):
        shutil.copy2(ASSETS/name,images/name)
        source=source.replace("assets/"+name,"images/"+name)
    (target/"article.qmd").write_text(source,encoding="utf-8")
    (target/"PUBLISHING.txt").write_text(
        "MEDIUM EDITION — Sexual violence in perspective\n\n"
        "1. Open article.html in a browser and copy the rendered article into Medium's editor.\n"
        "2. Put its title and subtitle in Medium's title/subtitle fields.\n"
        "3. Upload each PNG from images/ individually at its matching figure position. Copy the caption and add image alt text.\n"
        "4. Keep the source links. Review on mobile before publishing.\n"
        f"5. Full report: {published_url or 'awaiting publication'}. Check that it opens before publishing.\n"
        "6. The complete GitHub report is the canonical source. Set the Medium canonical URL after that page is live.\n\n"
        "This package is prepared for Medium. Publishing on Medium is a separate step.\n",
        encoding="utf-8")


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--published-url");args=parser.parse_args()
    manifest=verify_sources();DATA.mkdir(exist_ok=True);ASSETS.mkdir(exist_ok=True)
    who=prepare_who();unodc=prepare_unodc();prepare_uk();prepare_children();prepare_justice()
    (DATA/"source-register.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    register={
        "who-non-partner-sexual-violence.csv":{"source":"who-npsv-countries","population":"Women 15+","period":"Since age 15; 2023 model edition","unit":"Percent; 95% uncertainty bounds","method":"Portal proportions multiplied by 100"},
        "unodc-recorded-rates.csv":{"source":"unodc-workbook","population":"All sexes, all ages; national administrative returns","period":"2003–2024, availability varies","unit":"Recorded offences per 100,000 population","method":"Filter Violent offences / by type of offence / total sex and age / provided rates"},
        "england-wales-survey-trend.csv":{"source":"ons-trend-2025","population":"People aged 16–59; England and Wales households","period":"Last year; surveys YE March 2005–2025","unit":"Percent","method":"Downloaded ONS chart CSV; missing year preserved"},
        "england-wales-age-2025.csv":{"source":"ons-victims-2025-figure-3","population":"People aged 16+; England and Wales households","period":"Last year; YE March 2025","unit":"Percent","method":"Downloaded ONS chart CSV"},
        "england-wales-sexual-victimisation-2026.csv":{"source":"ons-latest-2026","population":"People aged 16+; England and Wales households","period":"Last year; YE March 2026","unit":"Percent","method":"Transcribed from bulletin section 9; redesigned measure"},
        "unicef-childhood-regions.csv":{"source":"unicef-release","population":"Girls and women alive at estimation","period":"Before age 18; 2024 release","unit":"Percent and millions of survivors","method":"Regional figures transcribed from official release"},
        "england-wales-childhood-2024.csv":{"source":"ons-childhood-2024-figure-1","population":"Adults 18+; England and Wales households","period":"Before age 18; survey YE March 2024","unit":"Percent","method":"Sexual-abuse row from ONS chart CSV"},
        "rape-outcome-maturity.csv":{"source":"home-office-outcomes-2026","population":"Recorded rape offence cohorts; England and Wales","period":"Cohorts YE March 2025 and 2026; July releases","unit":"Percent with charge/summons outcome at snapshot","method":"Transcribed from section 2.4; not convictions"},
    }
    (DATA/"dataset-register.json").write_text(json.dumps(register,indent=2),encoding="utf-8")
    medium(args.published_url)
    summary={"evidence_date":"2026-11-06","who_countries":len(who),"unodc_records":len(unodc),
             "who_population":"Women 15+; includes older adolescents","who_period":"Since age 15; 2023 model edition",
             "published_url":args.published_url,"status":"local review edition"}
    (DATA/"edition.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":main()
