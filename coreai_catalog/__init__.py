"""Core AI Catalog — discover, verify, and install Apple Core AI models.

Public API:
    from coreai_catalog import Catalog

    catalog = Catalog.load()
    catalog.recommend(task="ocr", device="iphone")
    catalog.compare("qwen3-vl-2b", "unlimited-ocr")
"""
from .api import Catalog

__all__ = ["Catalog"]
