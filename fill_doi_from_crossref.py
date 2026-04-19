"""
Autofill missing DOI fields in a BibTeX file using arXiv and Crossref.

Usage:
    python fill_doi_from_crossref.py INPUT_BIB OUTPUT_BIB UNRESOLVED_TXT
"""

import re
import sys
import time
import json
import html
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from difflib import SequenceMatcher
from urllib.parse import quote
from urllib.request import Request, urlopen

INPUT = sys.argv[1] if len(sys.argv) > 1 else "bibliography.bib"
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else "bibliography-with-doi.bib"
UNRES = sys.argv[3] if len(sys.argv) > 3 else "unresolved-doi.txt"

ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def split_entries(text: str):
    return re.split(r"(?=@\w+\{)", text)


def get_field(entry: str, field: str) -> str:
    m = re.search(rf"\b{field}\s*=\s*\{{(.+?)\}}", entry, re.I | re.S)
    return m.group(1).strip().replace("\n", " ") if m else ""


def normalize_latex(text: str) -> str:
    text = re.sub(r"\\[a-zA-Z]+\s*\{?([^}]*)\}?", r"\1", text)
    text = text.replace("{", "").replace("}", "")
    return text


def normalize(text: str) -> str:
    text = normalize_latex(text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    return text.lower().strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def parse_year(value) -> int | None:
    if value is None:
        return None
    s = str(value).strip()
    m = re.search(r"\b(1[0-9]{3}|20[0-9]{2}|21[0-9]{2})\b", s)
    return int(m.group(1)) if m else None


def first_author_surname(author_field: str) -> str:
    if not author_field:
        return ""
    first = author_field.split(" and ")[0].strip()
    if "," in first:
        surname = first.split(",")[0].strip()
    else:
        surname = first.split()[-1].strip()
    return normalize(surname)


def is_arxiv_entry(entry: str) -> bool:
    journal = get_field(entry, "journal").lower()
    eprint = get_field(entry, "eprint").lower()
    archiveprefix = get_field(entry, "archiveprefix").lower()
    note = get_field(entry, "note").lower()
    url = get_field(entry, "url").lower()

    return (
        "arxiv" in journal
        or "arxiv" in eprint
        or "arxiv" in archiveprefix
        or "arxiv" in note
        or "arxiv.org" in url
    )


def extract_arxiv_id(entry: str) -> str | None:
    candidates = [
        get_field(entry, "eprint"),
        get_field(entry, "journal"),
        get_field(entry, "note"),
        get_field(entry, "url"),
    ]

    patterns = [
        r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b",
        r"\b([a-z\-]+(?:\.[A-Z\-]+)?/\d{7}(?:v\d+)?)\b",
    ]

    for text in candidates:
        if not text:
            continue
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                return m.group(1).strip()

    return None


class ArxivMetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.doi = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta" or self.doi:
            return

        attr_dict = {k.lower(): v for k, v in attrs if v is not None}
        name = (attr_dict.get("name") or attr_dict.get("property") or "").lower()
        content = attr_dict.get("content", "").strip()

        if name == "citation_doi" and content:
            self.doi = content


def fetch_arxiv_doi(arxiv_id: str) -> str | None:
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id.strip())
    headers = {"User-Agent": "Mozilla/5.0 DOI BibTeX Helper"}

    # 1. Try the arXiv abstract page HTML first
    abs_url = f"https://arxiv.org/abs/{quote(arxiv_id)}"
    try:
        req = Request(abs_url, headers=headers)
        with urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", errors="ignore")

        parser = ArxivMetaParser()
        parser.feed(page)

        if parser.doi:
            return html.unescape(parser.doi.strip())

        # Fallback: DOI link visible in the HTML
        m = re.search(r'https?://doi\.org/([^"\'<>\s]+)', page, re.I)
        if m:
            return html.unescape(m.group(1).strip())

    except Exception:
        pass

    # 2. Fall back to the arXiv API XML
    api_url = f"https://export.arxiv.org/api/query?id_list={quote(arxiv_id)}"
    try:
        req = Request(api_url, headers=headers)
        with urlopen(req, timeout=30) as r:
            data = r.read()

        root = ET.fromstring(data)
        doi_el = root.find(".//arxiv:doi", ARXIV_NS)
        if doi_el is not None and doi_el.text:
            return doi_el.text.strip()

    except Exception:
        pass

    return None


def crossref_request(url: str):
    req = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 DOI BibTeX Helper"},
    )
    with urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_crossref_candidates(title: str, year: str, author: str, journal: str, arxiv_mode: bool):
    candidates = []

    title_q = quote(title)
    author_q = quote(author) if author else ""

    urls = []

    bib_query = title
    if author:
        bib_query += f" {author}"
    if journal:
        bib_query += f" {journal}"

    bib_q = quote(bib_query)

    if year and not arxiv_mode:
        urls.append(
            f"https://api.crossref.org/works?query.bibliographic={bib_q}&rows=10"
            f"&filter=from-pub-date:{year},until-pub-date:{year}"
        )

    url2 = f"https://api.crossref.org/works?query.title={title_q}&rows=15"
    if author_q:
        url2 += f"&query.author={author_q}"
    urls.append(url2)

    urls.append(f"https://api.crossref.org/works?query.title={title_q}&rows=20")
    urls.append(f"https://api.crossref.org/works?query.bibliographic={bib_q}&rows=20")

    seen_dois = set()

    for url in urls:
        try:
            data = crossref_request(url)
            items = data.get("message", {}).get("items", [])
            for it in items:
                doi = it.get("DOI")
                if doi and doi not in seen_dois:
                    seen_dois.add(doi)
                    candidates.append(it)
        except Exception:
            continue

        time.sleep(0.2)

    return candidates


def score_candidate(item, title: str, year: str, author: str, journal: str, arxiv_mode: bool):
    cand_title = " ".join(item.get("title", []))

    cand_year = None
    if item.get("published-print", {}).get("date-parts"):
        cand_year = item["published-print"]["date-parts"][0][0]
    elif item.get("published-online", {}).get("date-parts"):
        cand_year = item["published-online"]["date-parts"][0][0]
    elif item.get("issued", {}).get("date-parts"):
        cand_year = item["issued"]["date-parts"][0][0]

    cand_journal = " ".join(item.get("container-title", []))

    cand_authors = item.get("author", [])
    cand_first_author = ""
    if cand_authors:
        family = cand_authors[0].get("family", "") or cand_authors[0].get("name", "")
        cand_first_author = normalize(family)

    title_score = similarity(title, cand_title)
    journal_score = similarity(journal, cand_journal) if journal and cand_journal else 0.0

    score = title_score * 100.0

    year_i = parse_year(year)
    cand_year_i = parse_year(cand_year)

    if year_i is not None and cand_year_i is not None:
        if year_i == cand_year_i:
            score += 8.0
        elif abs(year_i - cand_year_i) == 1:
            score += 2.0
        elif abs(year_i - cand_year_i) > 3 and not arxiv_mode:
            score -= 8.0

    wanted_author = first_author_surname(author)
    if wanted_author and cand_first_author:
        if wanted_author == cand_first_author:
            score += 6.0

    if journal and cand_journal:
        score += journal_score * 10.0

    if normalize(title) == normalize(cand_title):
        score += 20.0

    return score, cand_title


def choose_best_doi(title: str, year: str, author: str, journal: str, entry: str):
    arxiv_mode = is_arxiv_entry(entry)

    # 1. Try arXiv first if this is an arXiv-based entry
    if arxiv_mode:
        arxiv_id = extract_arxiv_id(entry)
        if arxiv_id:
            doi = fetch_arxiv_doi(arxiv_id)
            if doi:
                return doi, f"found via arXiv ({arxiv_id})"

    # 2. Fall back to Crossref
    candidates = fetch_crossref_candidates(title, year, author, journal, arxiv_mode)

    if not candidates:
        return None, "no candidates from Crossref"

    best = None
    best_score = -1.0

    for item in candidates:
        score, cand_title = score_candidate(item, title, year, author, journal, arxiv_mode)
        if score > best_score:
            best_score = score
            best = item

    if not best:
        return None, "no acceptable match"

    best_title = " ".join(best.get("title", []))
    title_sim = similarity(title, best_title)

    if normalize(title) == normalize(best_title):
        return best.get("DOI"), "exact title match"

    if arxiv_mode and title_sim >= 0.88:
        return best.get("DOI"), f"accepted arXiv published-version match (similarity={title_sim:.3f})"

    if title_sim >= 0.93:
        return best.get("DOI"), f"accepted high-similarity title match (similarity={title_sim:.3f})"

    return None, f"best match below threshold (similarity={title_sim:.3f})"


def insert_doi(entry: str, doi: str) -> str:
    entry = entry.rstrip()

    if re.search(r"\bdoi\s*=", entry, re.I):
        entry = re.sub(
            r"\bdoi\s*=\s*\{[^}]*\}",
            f"doi = {{{doi}}}",
            entry,
            flags=re.I | re.S,
        )
        return entry + "\n"

    m = re.search(r"\}\s*$", entry, re.S)
    if not m:
        return entry + f"\n  doi = {{{doi}}}\n"

    body = entry[:m.start()].rstrip()

    if not body.endswith(","):
        body += ","

    return f"{body}\n  doi = {{{doi}}}\n}}\n"


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        text = f.read()

    entries = split_entries(text)
    out_entries = []
    unresolved = []

    for entry in entries:
        stripped = entry.strip()
        if not stripped:
            continue

        m = re.match(r"@(\w+)\{([^,]+),", stripped, re.I | re.S)
        if not m:
            out_entries.append(entry)
            continue

        typ, key = m.group(1).lower(), m.group(2)

        if re.search(r"\bdoi\s*=\s*\{", entry, re.I):
            out_entries.append(entry.rstrip() + "\n")
            continue

        title = get_field(entry, "title")
        year = get_field(entry, "year")
        author = get_field(entry, "author")
        journal = get_field(entry, "journal") or get_field(entry, "booktitle")

        if not title:
            unresolved.append((key, "missing title"))
            out_entries.append(entry.rstrip() + "\n")
            continue

        doi, reason = choose_best_doi(title, year, author, journal, entry)

        if doi:
            out_entries.append(insert_doi(entry, doi))
        else:
            unresolved.append((key, title, reason))
            out_entries.append(entry.rstrip() + "\n")

        time.sleep(0.2)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(e.rstrip("\n") for e in out_entries) + "\n")

    with open(UNRES, "w", encoding="utf-8") as f:
        for row in unresolved:
            f.write("\t".join(str(x) for x in row) + "\n")

    print(f"Wrote {OUTPUT} and {UNRES}")


if __name__ == "__main__":
    main()
