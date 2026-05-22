"""Extract lexical entries from the Glossary PDF (NION Part III)."""

from pathlib import Path


def extract_entries(pdf_path: Path) -> list[dict]:
    """Parse the glossary PDF and return a list of entry dicts.

    Each dict has keys matching the entries schema.
    Not yet implemented.
    """
    raise NotImplementedError
