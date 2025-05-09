# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import os.path
from collections.abc import Sequence

import anki.collection
from anki.models import NotetypeNameId
from aqt import gui_hooks, mw
from aqt.operations import CollectionOp

from .config_view import config_view as cfg
from .helpers.consts import ADDON_NAME
from .helpers.profiles import ProfileFurigana
from .note_type.bundled_files import BUNDLED_CSS_FILE, BundledCSSFile, get_file_version
from .note_type.files_in_col_media import (
    FileInCollection,
    find_ajt_scripts_in_collection,
)
from .note_type.imports import ensure_css_imported, ensure_js_imported


def not_recent_version(file: BundledCSSFile) -> bool:
    return file.version > get_file_version(file.path_in_col()).version


def save_to_col(file: BundledCSSFile) -> None:
    with open(file.path_in_col(), "w", encoding="utf-8") as of:
        of.write(file.text_content)


def is_debug_enabled() -> bool:
    return "QTWEBENGINE_REMOTE_DEBUGGING" in os.environ


def ensure_bundled_css_file_saved() -> None:
    """
    Save the AJT Japanese CSS file to the 'collection.media' folder.
    """
    if not_recent_version(BUNDLED_CSS_FILE) or is_debug_enabled():
        save_to_col(BUNDLED_CSS_FILE)
        print(f"Created new file: {BUNDLED_CSS_FILE.name_in_col}")


def collect_all_relevant_models() -> Sequence[NotetypeNameId]:
    """
    Find all note types (models) that require additional JS+CSS imports
    to enable the display of pitch accent information on mouse hover.
    """
    assert mw
    return [
        model
        for model in mw.col.models.all_names_and_ids()
        if any(
            profile.note_type.lower() in model.name.lower()
            for profile in cfg.iter_profiles()
            if isinstance(profile, ProfileFurigana)
        )
    ]


def ensure_imports_added_for_model(col: anki.collection.Collection, model: NotetypeNameId) -> bool:
    model_dict = col.models.get(model.id)
    if not model_dict:
        return False
    is_dirty = ensure_css_imported(model_dict)
    for template in model_dict["tmpls"]:
        for side in ("qfmt", "afmt"):
            is_dirty = ensure_js_imported(template, side) or is_dirty
    if is_dirty:
        col.models.update_dict(model_dict)
        print(f"Model {model.name} is dirty.")
    return is_dirty


def ensure_imports_added_op(
    col: anki.collection.Collection, models: Sequence[NotetypeNameId]
) -> anki.collection.OpChanges:
    assert mw
    pos = col.add_custom_undo_entry(f"{ADDON_NAME}: Add imports to {len(models)} models.")
    is_dirty = False
    for model in models:
        print(f"Relevant AJT note type: {model.name}")
        is_dirty = ensure_imports_added_for_model(col, model) or is_dirty
    return col.merge_undo_entries(pos) if is_dirty else anki.collection.OpChanges()


def ensure_imports_added(models: Sequence[NotetypeNameId]) -> None:
    assert mw
    CollectionOp(mw, lambda col: ensure_imports_added_op(col, models)).success(lambda _: None).run_in_background()


def remove_old_file_versions() -> None:
    assert mw
    saved_files: frozenset[FileInCollection] = find_ajt_scripts_in_collection() - {BUNDLED_CSS_FILE.name_in_col}
    for file in saved_files:
        if file.version < BUNDLED_CSS_FILE.version:
            os.unlink(os.path.join(mw.col.media.dir(), file.name))
            print(f"Removed old version: {file.name}")


def prepare_note_types() -> None:
    if not cfg.insert_scripts_into_templates:
        # Global switch (in Advanced settings, not shown in the GUI settings.)
        return
    if models := collect_all_relevant_models():
        # Add scripts to templates only if the user has profiles (tasks) where furigana needs to be generated.
        ensure_bundled_css_file_saved()
        ensure_imports_added(models)
        remove_old_file_versions()


def init():
    gui_hooks.profile_did_open.append(prepare_note_types)
