# Old Norse Tools

A Python toolkit for studying Old Norse, built around the three-volume
*A New Introduction to Old Norse* published by the
[Viking Society for Northern Research](https://vsnr.org) (VSNR).

The project has three phases:

1. **Lexical database** — extract headwords, parts of speech, definitions,
   and grammatical information from the VSNR Glossary PDF into a structured
   SQLite database.
2. **Morphological parser** — derive inflection rules from the VSNR Grammar's
   numbered paradigm tables, link them to glossary entries, and generate all
   inflected forms for each headword. The parser can identify the grammatical
   role (case, number, gender, tense, mood, etc.) of any word form.
3. **Text analysis tool** — given any Old Norse text, tokenize it and display
   a word-by-word morphological and lexical analysis in the style of the
   annotated Reader texts, similar in spirit to the
   [Perseus Digital Library](https://www.perseus.tufts.edu) tools for Latin
   and Greek.

---

## Source materials

This project relies entirely on freely available PDFs published by the
**Viking Society for Northern Research** at University College London.
All three volumes are available without charge from [vsnr.org](https://vsnr.org).

| Volume | Author | Description |
|--------|--------|-------------|
| [Part I: Grammar](https://vsnr.org/wp-content/uploads/2021/11/NION-1.pdf) | Michael Barnes | Reference grammar with numbered paradigm tables for nouns, adjectives, pronouns, and verbs |
| [Part II: Reader](https://vsnr.org/wp-content/uploads/2021/11/NION-II-2011.pdf) | Edited by Anthony Faulkes | Graded Old Norse texts with full morphological commentary on Text I (*Hrólfs saga kraka*) |
| [Part III: Glossary](https://vsnr.org/wp-content/uploads/2021/11/NION-Glossary-2011.pdf) | Compiled by Anthony Faulkes | Complete glossary with parts of speech, definitions, grammar cross-references, and text citations |

> **Credit:** *A New Introduction to Old Norse* is the work of the Viking Society
> for Northern Research and its contributors. The grammar is by Michael Barnes;
> the glossary and index are compiled by Anthony Faulkes, with supplements by
> Michael Barnes. The reader texts are annotated by Michael Barnes, Anthony
> Faulkes, Richard Perkins, Rory McTurk, Alison Finlay, Diana Whaley, David
> Ashurst, Carl Phelpstead, Peter Foote, Elizabeth Ashman Rowe, and John
> McKinnell. This software project parses those freely distributed PDFs for
> personal study purposes and does not reproduce their content.

---

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install uv (if not already installed)
brew install uv        # macOS
# or: pip install uv

# Install project dependencies
make install

# Download the PDFs from vsnr.org
make download

# Build the database
make build

# Run tests
make test
```

---

## Usage

### Build the database

```bash
nion-build
# or with custom paths:
nion-build --pdfs path/to/pdfs --db path/to/output.db
```

### Analyze a text

```bash
# Pass text directly
nion-analyze "konungr spyrr um mat ok drykk"

# Or from a file
nion-analyze --file my_text.txt
```

Example output:

```
konungr
  konungr (noun m) — nom.sg — king, the king

spyrr
  spyrja (verb weak) — 2sg pres — ask
  spyrja (verb weak) — 3sg pres — ask

um
  ?  no match

mat
  matr (noun m) — acc.sg — food

ok
  ?  no match

drykk
  drykkr (noun m) — acc.sg — drink, draught
```

Words with multiple analyses (like `spyrr`, which is ambiguous between 2nd and 3rd
person) show all possibilities. Function words and uninflected particles not covered
by the paradigm tables show `?  no match`.

---

## Project structure

```
src/nion/
├── encoding.py          # PDF artifact correction and search normalization
├── db/schema.py         # SQLite schema and connection helper
├── extractors/
│   ├── grammar.py       # Parse paradigm tables from the Grammar PDF
│   ├── glossary.py      # Parse lexical entries from the Glossary PDF
│   └── reader.py        # Parse Text I annotations from the Reader PDF
├── morphology/
│   ├── generator.py     # Generate all inflected forms from a paradigm
│   └── parser.py        # Look up surface forms in the database
└── tools/
    └── analyze.py       # CLI text analysis tool (Phase 3)
```

---

## License

This software is released under the MIT License. See [LICENSE](LICENSE).

The PDF source materials are © Viking Society for Northern Research and are
used here solely for personal, non-commercial study. Please visit
[vsnr.org](https://vsnr.org) to download them directly.
