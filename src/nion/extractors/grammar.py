"""Extract numbered paradigm tables from the Grammar PDF (NION Part I)."""

from pathlib import Path


def extract_paradigms(pdf_path: Path) -> list[dict]:
    """Parse the grammar PDF and return a list of paradigm dicts.

    Each dict has keys matching the paradigms + paradigm_forms schema.
    Not yet implemented.
    """
    raise NotImplementedError
