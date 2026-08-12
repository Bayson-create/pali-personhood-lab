"""Standalone, read-only hybrid search service for the Sutta corpora.

The package deliberately lives outside ``api/``.  It has no dependency on
the application database, authentication, or mutable reader overlays.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
