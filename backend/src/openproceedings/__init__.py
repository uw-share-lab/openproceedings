"""openproceedings: exact, reproducible Boolean search over NeurIPS, ICLR and ICML titles and abstracts."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("openproceedings")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0"
