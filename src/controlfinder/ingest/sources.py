"""Pinned source files: downloaded once, then checked against a sha256 on every run.

The OSCAL catalog is pinned to an oscal-content commit, and the tokenizer to the Hugging Face
revision of the embedding model we use, so a rerun months from now parses exactly the same
bytes. A checksum mismatch stops the run, because every number downstream would silently
change with the bytes.
"""

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAW = Path("data/raw")
OSCAL_COMMIT = "f0de6d8d8c059d374f15e0ae07508d82e370fc1d"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"


@dataclass(frozen=True)
class Source:
    url: str
    sha256: str
    path: Path


CATALOG = Source(
    url=f"https://raw.githubusercontent.com/usnistgov/oscal-content/{OSCAL_COMMIT}"
    "/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
    sha256="64ca6b4161de51ab6af098a7d101d326f14c95e1abf721396cd8a049e8115eeb",
    path=RAW / "NIST_SP-800-53_rev5_catalog.json",
)
TOKENIZER = Source(
    url=f"https://huggingface.co/{EMBED_MODEL}/resolve/{EMBED_REVISION}/tokenizer.json",
    sha256="d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    path=RAW / "bge-small-en-v1.5-tokenizer.json",
)
# The CSF 2.0 "Informative References in the Core" xlsx, downloaded 2026-10-29. Its endpoint
# isn't versioned, so the file is committed; a fresh download with other bytes fails the check.
CSF = Source(
    url="https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all",
    sha256="a998dccb1eed72400fd628390e6030dcbb910b5d5850909c4c65c30005efb55e",
    path=RAW / "csf2.xlsx",
)


def fetch(source: Source) -> Path:
    """Return the local copy of `source`, downloading it first if needed."""
    if source.path.exists():
        data = source.path.read_bytes()
    else:
        with urllib.request.urlopen(source.url) as response:
            data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != source.sha256:
        raise RuntimeError(
            f"{source.url}: sha256 is {digest}, pinned {source.sha256}. "
            f"If {source.path} exists, delete it to download again."
        )
    if not source.path.exists():
        source.path.parent.mkdir(parents=True, exist_ok=True)
        source.path.write_bytes(data)
    return source.path
