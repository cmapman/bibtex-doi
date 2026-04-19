# DOI Autofill for BibTeX

A Python script that scans a `.bib` file, looks up missing DOI values, inserts found DOIs into BibTeX entries, and writes unresolved items to a separate report.

The script currently supports the following BibTeX entry types:

- `@article`
- `@book`
- `@incollection`
- `@inproceedings`

## Features

- fills missing DOI fields automatically
- preserves existing DOI fields
- supports multiple BibTeX entry types
- uses metadata such as title, year, author, and journal/booktitle for matching
- detects arXiv-based entries and tries to resolve DOI directly from arXiv
- falls back to Crossref when needed
- writes unresolved entries to a separate text file

## Script

```
fill_doi_from_crossref.py
````

## Requirements

* Python 3.8+
* internet connection
* access to:

  * the arXiv website / API
  * the Crossref API

No third-party packages are required.

## How it works

For each BibTeX entry without a `doi` field, the script:

1. extracts metadata such as:

   * `title`
   * `year`
   * `author`
   * `journal` or `booktitle`
2. checks whether the entry looks like an arXiv record
3. if it is an arXiv entry:

   * extracts the arXiv identifier
   * checks the arXiv abstract page for a DOI
   * falls back to the arXiv API if needed
4. if no DOI is found there, queries Crossref
5. ranks candidate matches using:

   * normalized title similarity
   * year agreement
   * first-author agreement
   * journal or container-title similarity
6. inserts the DOI if a confident match is found
7. writes unresolved entries to a separate report

## Supported entry types

It will attempt DOI lookup for any BibTeX entry that has enough metadata to search, including books, conference papers, and book chapters. In practice:

* `@article` usually works best
* `@inproceedings` and `@incollection` often work, but matching can be less consistent
* `@book` can work, though book metadata in Crossref may be noisier

## Usage

```
python fill_doi_from_crossref.py INPUT_BIB OUTPUT_BIB UNRESOLVED_TXT
```

## Example

Suppose your input file is:

```
bibliography.bib
```

Run:

```
python fill_doi_from_crossref.py bibliography.bib bibliography-with-doi.bib unresolved-doi.txt
```

This will create:

* `bibliography-with-doi.bib` — your bibliography with DOI fields added where found
* `unresolved-doi.txt` — a list of entries that could not be resolved safely

## Example input

```bibtex
@article{koshkarov2024novel,
  title={Novel algorithm for comparing phylogenetic trees with different but overlapping taxa},
  author={Koshkarov, Aleksandr and Tahiri, Nadia},
  journal={Symmetry},
  volume={16},
  number={7},
  pages={790},
  year={2024},
  publisher={MDPI}
}
```

## Example output

```bibtex
@article{koshkarov2024novel,
  title={Novel algorithm for comparing phylogenetic trees with different but overlapping taxa},
  author={Koshkarov, Aleksandr and Tahiri, Nadia},
  journal={Symmetry},
  volume={16},
  number={7},
  pages={790},
  year={2024},
  publisher={MDPI},
  doi={10.3390/sym16070790}
}
```

## ArXiv support

The script has dedicated handling for arXiv-style entries.

If an entry contains an arXiv identifier, the script will:

1. detect that the entry refers to arXiv
2. extract the arXiv identifier, such as `1708.02626`
3. check the arXiv abstract page for a DOI
4. fall back to the arXiv API if needed
5. fall back to Crossref if arXiv does not expose a DOI

## Matching strategy

The script uses a simple scoring approach to avoid inserting unsafe DOI values.

Signals include:

* exact normalized title match
* high title similarity
* matching or near-matching year
* matching first author surname
* similarity between BibTeX `journal` / `booktitle` and Crossref container title

If the best match is not strong enough, the entry is left unresolved instead of forcing a DOI.

## Output files

### 1. Updated BibTeX file

The script writes a new `.bib` file with DOI fields inserted into matched entries.

Existing DOI fields are preserved and left unchanged.

### 2. Unresolved report

The unresolved file contains tab-separated rows like:

```text
entry_key    entry_title    reason
```

Typical reasons include:

* missing title
* no candidates from Crossref
* best match below threshold
* arXiv DOI not available
* network or API error

## Notes and limitations

* some records do not have a DOI
* books, chapters, and proceedings entries can be harder to match than articles
* metadata in BibTeX files is sometimes incomplete or inconsistent
* Crossref metadata is not always complete or perfectly normalized
* the script intentionally prefers leaving an entry unresolved over inserting a doubtful DOI

## Good practice

After running the script:

1. review `bibliography-with-doi.bib`
2. inspect `unresolved-doi.txt`
3. manually verify important or ambiguous entries

## License

[MIT](https://github.com/cmapman/bibtex-doi/blob/main/LICENSE)
