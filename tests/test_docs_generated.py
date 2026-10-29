"""Guards the "tables are generated, never typed" rule: every generated region in the docs
must equal what results/*.json renders to right now. Fix a failure with `make docs`.
"""

import pytest

from controlfinder.docgen import DOC_PATHS, REGION, render


@pytest.mark.parametrize("path", [p for p in DOC_PATHS if p.exists()], ids=str)
def test_generated_regions_match_results(path):
    text = path.read_text()
    assert render(text) == text


def test_docs_contain_generated_regions():
    assert any(REGION.search(p.read_text()) for p in DOC_PATHS if p.exists())
