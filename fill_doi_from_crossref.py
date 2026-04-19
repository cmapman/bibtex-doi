import re, sys, time, json
from urllib.parse import quote
from urllib.request import Request, urlopen

INPUT = sys.argv[1] if len(sys.argv) > 1 else 'bibliography.bib'
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else 'bibliography-with-doi.bib'
UNRES = sys.argv[3] if len(sys.argv) > 3 else 'unresolved-doi.txt'

with open(INPUT, 'r', encoding='utf-8') as f:
    text = f.read()

entries = re.split(r'(?=@\w+\{)', text)

def get_field(entry, field):
    m = re.search(rf'\b{field}\s*=\s*\{{(.+?)\}}', entry, re.I | re.S)
    return m.group(1).strip().replace('\n', ' ') if m else ''

def normalize(s):
    s = re.sub(r'\\[a-zA-Z]+\s*\{?([^}]*)\}?', r'\1', s)
    s = re.sub(r'[^A-Za-z0-9]+', ' ', s).lower().strip()
    return re.sub(r'\s+', ' ', s)

out_entries = []
unresolved = []

for entry in entries:
    m = re.match(r'@(\w+)\{([^,]+),', entry.strip(), re.I | re.S)
    if not m:
        if entry.strip():
            out_entries.append(entry)
        continue

    typ, key = m.group(1).lower(), m.group(2)

    if re.search(r'\bdoi\s*=\s*\{', entry, re.I):
        out_entries.append(entry)
        continue

    title = get_field(entry, 'title')
    year = get_field(entry, 'year')

    if not title:
        unresolved.append((key, 'missing title'))
        out_entries.append(entry)
        continue

    query = quote(title)
    url = f'https://api.crossref.org/works?query.title={query}&rows=5'
    if year:
        url += f'&filter=from-pub-date:{year},until-pub-date:{year}'

    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 DOI bibtex helper'})
    doi = None
    reason = 'no match'

    try:
        with urlopen(req, timeout=30) as r:
            data = json.load(r)

        want = normalize(title)
        items = data.get('message', {}).get('items', [])

        for it in items:
            cand_title = ' '.join(it.get('title', []))
            if normalize(cand_title) == want:
                doi = it.get('DOI')
                break

        if not doi and items:
            for it in items:
                cand_title = ' '.join(it.get('title', []))
                cn = normalize(cand_title)
                if want in cn or cn in want:
                    doi = it.get('DOI')
                    break

    except Exception as e:
        reason = str(e)

    if doi:
        if entry.rstrip().endswith('}'):
            entry = entry.rstrip()[:-1] + f",\n  doi = {{{doi}}}\n}}\n"
        else:
            entry += f"\n  doi = {{{doi}}}\n"
    else:
        unresolved.append((key, title, reason))

    out_entries.append(entry)
    time.sleep(0.2)

with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_entries))

with open(UNRES, 'w', encoding='utf-8') as f:
    for row in unresolved:
        f.write('\t'.join(row) + '\n')

print(f'Wrote {OUTPUT} and {UNRES}')