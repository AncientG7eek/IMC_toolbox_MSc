"""IMC Curator: a curation toolkit for Imaging Mass Cytometry datasets."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("imc-curator")
except PackageNotFoundError:
    # Running from an uninstalled source checkout.
    __version__ = "0.1.0"
