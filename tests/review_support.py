"""Shared helpers for review-viewer tests. Synthetic, procedurally generated, non-biometric only."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from frp.review.records import ReviewMode
from frp.review.session import ReviewController
from frp.review.store import ReviewCatalogue, ReviewItem, ReviewStore


def make_demo_store(root: Path) -> ReviewStore:
    from frp.review.demo import create_demo_store

    create_demo_store(root)
    return ReviewStore(root)


def open_session(
    store: ReviewStore, mode: ReviewMode, reviewer: str = "RV-01", **kwargs: Any
) -> ReviewController:
    return ReviewController.open(store, mode=mode, reviewer_role_code=reviewer, **kwargs)


def rewrite_catalogue(store: ReviewStore, **update: Any) -> None:
    """Replace the catalogue file (tests only; the store API never replaces it)."""
    edit_catalogue(store, lambda data: data.update(update))


def edit_catalogue(store: ReviewStore, edit: Callable[[dict[str, Any]], None]) -> None:
    """Apply ``edit`` to the catalogue's JSON and replace the file (tests only)."""
    data = json.loads(store.load_catalogue().model_dump_json())
    edit(data)
    path = store.root / "catalogue.json"
    os.remove(path)
    path.write_text(json.dumps(data), encoding="utf-8")


def find_item(catalogue: ReviewCatalogue, **criteria: Any) -> ReviewItem:
    for item in catalogue.items:
        if all(
            (item.output_media is not None) == value
            if name == "has_output"
            else getattr(item, name) == value
            for name, value in criteria.items()
        ):
            return item
    raise LookupError(criteria)
