"""Check source integrity, report figures, downloads, and dataset registration."""
import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
QMD_FILES = ["index.qmd", "worldwide.qmd", "uk.qmd", "children.qmd", "justice.qmd"]


def require(condition, message: str):
    if not condition:
        raise AssertionError(message)


def read_csv(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def numeric(row, key):
    return float(row[key])


def page_text(name):
    return (ROOT / name).read_text(encoding="utf-8")


def main():
    source_manifest = json.loads((ROOT / "sources" / "manifest.json").read_text(encoding="utf-8"))
    vendored = [source for source in source_manifest.get("sources", []) if source.get("file")]
    require(vendored, "sources/manifest.json has no vendored source files to validate.")
    for source in vendored:
        relative = Path(source["file"].replace("\\", "/"))
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT.resolve()), f"Source path escapes the repository: {source['file']}")
        require(path.is_file(), f"Vendored source is missing: {source['file']}")
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == source.get("sha256"),
                f"Vendored source hash changed: {source['file']}")
        require(len(raw) == source.get("bytes"), f"Vendored source size changed: {source['file']}")

    who = read_csv("who-non-partner-sexual-violence.csv")
    require(len(who) == 138 and len({row["code"] for row in who}) == 138,
            "WHO estimate file no longer contains 138 unique countries and areas.")
    uk_who = next((row for row in who if row["code"] == "GBR"), None)
    require(uk_who is not None and round(numeric(uk_who, "percent"), 1) == 7.3
            and round(numeric(uk_who, "lower_95"), 1) == 4.6
            and round(numeric(uk_who, "upper_95"), 1) == 11.0,
            "WHO UK estimate or its 95% interval no longer matches the report.")

    trend = read_csv("england-wales-survey-trend.csv")
    trend_by_year = {int(row["year_ending_march"]): row for row in trend}
    require(max(trend_by_year) == 2025 and trend_by_year[2021]["percent"] == "",
            "Historical survey trend must end in 2025 and retain the missing 2021 estimate.")
    for year, expected in {2015: 1.7, 2024: 2.6, 2025: 2.4}.items():
        require(round(numeric(trend_by_year[year], "percent"), 1) == expected,
                f"Historical survey estimate for {year} no longer matches the report.")

    recorded = read_csv("unodc-recorded-rates.csv")
    recorded_keys = [(row["code"], row["year"], row["category"]) for row in recorded]
    require(len(recorded_keys) == len(set(recorded_keys)), "UNODC data contains duplicate code/year/category rows.")
    require(all(row["code"] != "GBR" for row in recorded),
            "UNODC data must not invent an aggregate GBR police-recorded series.")

    latest = read_csv("england-wales-sexual-victimisation-2026.csv")
    latest_by_population = {row["population"]: row for row in latest}
    latest_expected = {
        "All people aged 16+": 2.1,
        "Women aged 16+": 2.8,
        "Men aged 16+": 1.4,
    }
    require(set(latest_by_population) == set(latest_expected), "Latest CSEW estimate populations changed.")
    for population, expected in latest_expected.items():
        require(round(numeric(latest_by_population[population], "percent"), 1) == expected,
                f"Latest CSEW estimate changed for {population}.")
    require("**2.1% of people aged 16 and over**" in page_text("uk.qmd"),
            "UK page no longer states the derived 2.1% all-people estimate.")
    require("**2.8% for women**" in page_text("uk.qmd") and "**1.4% for men**" in page_text("uk.qmd"),
            "UK page no longer states the derived women/men estimates.")

    childhood = read_csv("england-wales-childhood-2024.csv")
    childhood_by_population = {row["population"]: row for row in childhood}
    childhood_expected = {"All adults aged 18+": 9.1, "Women aged 18+": 13.9, "Men aged 18+": 4.1}
    require(set(childhood_by_population) == set(childhood_expected), "Childhood survey populations changed.")
    for population, expected in childhood_expected.items():
        require(round(numeric(childhood_by_population[population], "percent"), 1) == expected,
                f"Childhood estimate changed for {population}.")
    children_text = page_text("children.qmd")
    for expected in childhood_expected.values():
        require(f"{expected:.1f}%" in children_text, f"Childhood page is missing the derived {expected:.1f}% figure.")

    age = read_csv("england-wales-age-2025.csv")
    require(len(age) == 8 and all(numeric(row, "percent") >= 0 for row in age),
            "Age-breakdown data has unexpected rows or invalid prevalence values.")
    highest_age = max(age, key=lambda row: numeric(row, "percent"))
    require(highest_age["age_group"] == "20 to 24 years" and numeric(highest_age, "percent") == 6.1,
            "The highest age-band estimate no longer matches the underlying age data.")

    unicef = read_csv("unicef-childhood-regions.csv")
    require(len(unicef) == 7 and all(row["publication_year"] == "2024" for row in unicef),
            "UNICEF regional data no longer contains the seven 2024 regional estimates.")
    require(all(0 <= numeric(row, "percent") <= 100 and numeric(row, "survivors_millions") > 0 for row in unicef),
            "UNICEF regional prevalence or survivor counts contain invalid values.")
    regional_values = {
        row["region"]: (int(row["percent"]), int(row["survivors_millions"]))
        for row in unicef
    }
    expected_regional_values = {
        "Sub-Saharan Africa": (22, 79),
        "Eastern & South-Eastern Asia": (8, 75),
        "Central & Southern Asia": (9, 73),
        "Europe & Northern America": (14, 68),
        "Latin America & Caribbean": (18, 45),
        "Northern Africa & Western Asia": (15, 29),
        "Oceania": (34, 6),
    }
    require(regional_values == expected_regional_values,
            "UNICEF regional percentages or survivor counts no longer match the source data used in the figure.")

    maturity = read_csv("rape-outcome-maturity.csv")
    maturity_by_key = {(row["recorded_cohort"], row["snapshot"]): numeric(row, "charge_summons_percent") for row in maturity}
    require(maturity_by_key.get(("YE March 2025", "First published July 2025")) == 2.8
            and maturity_by_key.get(("YE March 2025", "Updated July 2026")) == 5.2
            and maturity_by_key.get(("YE March 2026", "First published July 2026")) == 3.4,
            "Rape charge/summons maturity rates no longer match the report.")
    justice_text = page_text("justice.qmd")
    for claim in ["**3.4% of rape offences recorded in YE March 2026**", "**2.8% when first published to 5.2%"]:
        require(claim in justice_text, f"Justice page is missing an outcome-maturity claim: {claim}")

    jurisdiction = read_csv("uk-jurisdiction-snapshots.csv")
    jurisdiction_counts = {row["jurisdiction"]: int(row["recorded_sexual_offences"]) for row in jurisdiction}
    expected_jurisdiction_counts = {
        "England and Wales": 218994,
        "Scotland": 16430,
        "Northern Ireland": 4459,
    }
    require(jurisdiction_counts == expected_jurisdiction_counts,
            "Jurisdiction snapshot counts no longer match the report.")
    uk_text = page_text("uk.qmd")
    for expected in expected_jurisdiction_counts.values():
        require(f"{expected:,}" in uk_text, f"UK page is missing the derived recorded count {expected:,}.")

    index_text = page_text("index.qmd")
    worldwide_text = page_text("worldwide.qmd")
    for text, claim in [
        (index_text, "**138**"),
        (index_text, "**2.1%**"),
        (index_text, "**9.1%**"),
        (index_text, "**7.3%**"),
        (worldwide_text, "**138 countries and areas**"),
        (worldwide_text, "**7.3% (4.6%–11.0%)**"),
    ]:
        require(claim in text, f"Summary/worldwide claim is missing or changed: {claim}")

    register = json.loads((DATA / "dataset-register.json").read_text(encoding="utf-8"))
    require(register, "data/dataset-register.json has no registered datasets.")
    for name in register:
        require((DATA / name).is_file(), f"Registered dataset is missing: data/{name}")

    linked_downloads = set()
    for name in QMD_FILES:
        page = ROOT / name
        require(page.is_file(), f"Report source page is missing: {name}")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path.startswith("data/"):
                continue
            linked_downloads.add(url.path)
            require((ROOT / unquote(url.path)).is_file(), f"Data download link does not exist: {target}")
    require(linked_downloads, "No reader-facing data download links were found in the report pages.")

    print(
        f"Report QA passed: {len(vendored)} source hashes, survey/WHO/UNICEF/justice figures, "
        f"{len(linked_downloads)} data downloads, and {len(register)} registered datasets."
    )


if __name__ == "__main__":
    main()