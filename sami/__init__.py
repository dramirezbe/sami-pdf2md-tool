"""sami — Smart Automated Markdown Interpreter."""

try:
    from sami._version import __version__
except ImportError:
    from importlib.metadata import version as _v, PackageNotFoundError

    try:
        __version__ = _v("sami-pdf2md-tool")
    except PackageNotFoundError:
        __version__ = "0.0.0+unknown"
