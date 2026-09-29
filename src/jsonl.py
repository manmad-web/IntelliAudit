"""records.jsonl files are committed gzipped (the US one is ~160 MB, over GitHub's
file limit). Readers go through open_text(), which falls back to <path>.gz."""
import gzip, os


def open_text(path):
    if os.path.exists(path):
        return open(path)
    if os.path.exists(path + ".gz"):
        return gzip.open(path + ".gz", "rt")
    raise FileNotFoundError(path)


def gzip_copy(path):
    """Write <path>.gz deterministically (mtime 0) so rebuilds stay byte-identical."""
    with open(path, "rb") as f, open(path + ".gz", "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as g:
            g.write(f.read())
