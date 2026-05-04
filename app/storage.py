from __future__ import annotations

import json
import re
import shutil
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

# 磁盘标准文件名（与需求文档一致）
FILENAME_BY_KEY: Dict[str, str] = {
    "whitepaper": "whitepaper.md",
    "master_library": "Conlang_Master_Library.json",
    "mapping_rules": "Mapping_Rules.csv",
    "translation_history": "Translation_History.json",
}

DEFAULT_PROJECT_NAME = "Nikki Conlang Forge"

DEFAULT_CONFIG: Dict[str, Any] = {
    "project_name": DEFAULT_PROJECT_NAME,
    "languages": [],
}


def _invalid_windows_char_re() -> re.Pattern[str]:
    return re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class JsonStorage:
    """使用 data/config.json + 每语言子目录管理资料。"""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.base_dir / "config.json"
        self._legacy_app_state = self.base_dir / "app_state.json"

    def load_state(self) -> Dict[str, Any]:
        """兼容旧称：返回完整应用配置（含 languages）。"""
        return self.load_config()

    def save_state(self, state: Dict[str, Any]) -> None:
        self.save_config(state)

    def load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            with self.config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if "languages" not in data or not isinstance(data["languages"], list):
                data["languages"] = []
            self._normalize_language_records(data["languages"])
            return data

        if self._legacy_app_state.exists():
            migrated = self._migrate_from_app_state(self._legacy_app_state)
            self.save_config(migrated)
            return migrated

        state = deepcopy(DEFAULT_CONFIG)
        lang = self._bootstrap_language("默认语言")
        state["languages"] = [lang]
        self._init_language_package(lang)
        self.save_config(state)
        return state

    def save_config(self, state: Dict[str, Any]) -> None:
        with self.config_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)

    def sanitize_folder_name(self, name: str) -> str:
        text = (name or "").strip().rstrip(".")
        if not text:
            text = "语言"
        text = _invalid_windows_char_re().sub("_", text)
        if text in (".", ".."):
            text = "语言"
        return text[:120]

    def existing_folder_names(self, exclude: Optional[str] = None) -> set[str]:
        out: set[str] = set()
        if not self.base_dir.is_dir():
            return out
        for child in self.base_dir.iterdir():
            if not child.is_dir():
                continue
            if child.name == "__pycache__":
                continue
            if exclude and child.name == exclude:
                continue
            out.add(child.name)
        return out

    def ensure_unique_folder_name(self, desired: str, exclude: Optional[str] = None) -> str:
        base = self.sanitize_folder_name(desired)
        used = self.existing_folder_names(exclude=exclude)
        if base not in used:
            return base
        n = 2
        while f"{base}_{n}" in used:
            n += 1
        return f"{base}_{n}"

    def new_language_id(self) -> str:
        """生成唯一语言 ID（UUID4）。"""
        return str(uuid.uuid4())

    def language_dir(self, language: Dict[str, Any]) -> Path:
        return self.base_dir / language["folder"]

    def asset_path(self, language: Dict[str, Any], key: str) -> Path:
        fname = FILENAME_BY_KEY[key]
        return self.language_dir(language) / fname

    def paths_for_language(self, language: Dict[str, Any]) -> Dict[str, Path]:
        return {k: self.asset_path(language, k) for k in FILENAME_BY_KEY}

    def path_strings_for_dialog(self, language: Dict[str, Any]) -> Dict[str, str]:
        """若标准路径上存在文件则显示，供「导入资料」对话框预填。"""
        out: Dict[str, str] = {}
        for key in FILENAME_BY_KEY:
            p = self.asset_path(language, key)
            out[key] = str(p.resolve()) if p.is_file() else ""
        return out

    def ensure_unique_language_name(
        self, desired_name: str, languages: List[Dict[str, Any]]
    ) -> str:
        existing = {item.get("name", "") for item in languages}
        name = (desired_name or "").strip() or "新语言"
        if name not in existing:
            return name
        n = 2
        while f"{name} {n}" in existing:
            n += 1
        return f"{name} {n}"

    def _normalize_language_records(self, languages: List[Dict[str, Any]]) -> None:
        used_folders: set[str] = set(self.existing_folder_names())
        for lang in languages:
            lang.pop("files", None)
            if not str(lang.get("id", "")).strip():
                lang["id"] = self.new_language_id()

            folder = str(lang.get("folder", "")).strip()
            if not folder:
                display = (lang.get("name") or "语言").strip() or "语言"
                base = self.sanitize_folder_name(display)
                candidate = base
                n = 2
                while candidate in used_folders:
                    candidate = f"{base}_{n}"
                    n += 1
                lang["folder"] = candidate
                used_folders.add(candidate)
            else:
                used_folders.add(folder)

            lang.setdefault("name", "语言")
            lang.setdefault("notes", "")
            lang.setdefault("icon", "")

    def _bootstrap_language(self, name: str) -> Dict[str, Any]:
        folder = self.ensure_unique_folder_name(name)
        return {
            "id": self.new_language_id(),
            "name": name.strip() or "默认语言",
            "folder": folder,
            "notes": "",
            "icon": "",
        }

    def create_language_record(self, desired_name: str, languages: List[Dict[str, Any]]) -> Dict[str, Any]:
        name = self.ensure_unique_language_name((desired_name or "").strip() or "新语言", languages)
        folder = self.ensure_unique_folder_name(name)
        language = {
            "id": self.new_language_id(),
            "name": name,
            "folder": folder,
            "notes": "",
            "icon": "",
        }
        self._init_language_package(language)
        return language

    def export_language_pack_zip(self, language: Dict[str, Any], zip_path: Path) -> tuple[int, str]:
        import zipfile

        count = 0
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for key, arcname in FILENAME_BY_KEY.items():
                p = self.asset_path(language, key)
                if p.is_file():
                    zf.write(p, arcname=arcname)
                    count += 1
        return count, ""

    def import_language_pack_zip(self, language: Dict[str, Any], zip_path: Path) -> tuple[int, str]:
        import zipfile

        archive_aliases: Dict[str, str] = {
            "whitepaper.md": "whitepaper",
            "whitepaper.txt": "whitepaper",
            "Conlang_Master_Library.json": "master_library",
            "Mapping_Rules.csv": "mapping_rules",
            "Translation_History.json": "translation_history",
        }
        lang_dir = self.language_dir(language)
        lang_dir.mkdir(parents=True, exist_ok=True)
        keys_written: set[str] = set()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                base = Path(member.filename).name
                key = archive_aliases.get(base)
                if key is None:
                    continue
                data = zf.read(member.filename)
                dest = self.asset_path(language, key)
                dest.write_bytes(data)
                keys_written.add(key)
        return len(keys_written), ""

    def _init_language_package(self, language: Dict[str, Any]) -> None:
        lang_dir = self.language_dir(language)
        lang_dir.mkdir(parents=True, exist_ok=True)

        wp = self.asset_path(language, "whitepaper")
        if not wp.is_file():
            wp.write_text(
                "# 种族语言逻辑白皮书\n\n（在此编写语言逻辑与约束；阶段二已自动创建占位文件。）\n",
                encoding="utf-8",
            )

        master = self.asset_path(language, "master_library")
        if not master.is_file():
            master.write_text("{}\n", encoding="utf-8")

        mapping = self.asset_path(language, "mapping_rules")
        if not mapping.is_file():
            mapping.write_text("自创语词汇,IPA音标,TTS友好拼写\n", encoding="utf-8")

        history = self.asset_path(language, "translation_history")
        if not history.is_file():
            history.write_text("{}\n", encoding="utf-8")

    def import_external_files(self, language: Dict[str, Any], paths: Dict[str, str]) -> None:
        """将对话框中选中的外部文件复制到语言包标准路径。"""
        lang_dir = self.language_dir(language)
        lang_dir.mkdir(parents=True, exist_ok=True)
        for key, src in paths.items():
            src = (src or "").strip()
            if not src:
                continue
            src_path = Path(src)
            if not src_path.is_file():
                continue
            dest = self.asset_path(language, key)
            shutil.copy2(src_path, dest)

    def _migrate_from_app_state(self, legacy_path: Path) -> Dict[str, Any]:
        with legacy_path.open("r", encoding="utf-8") as handle:
            old = json.load(handle)

        project_name = old.get("project_name", DEFAULT_PROJECT_NAME)
        languages_out: List[Dict[str, Any]] = []

        for item in old.get("languages", []) or []:
            name = (item.get("name") or "语言").strip() or "语言"
            folder = self.ensure_unique_folder_name(name)
            record = {
                "id": str(item.get("id") or self.new_language_id()),
                "name": name,
                "folder": folder,
                "notes": item.get("notes", "") or "",
            }
            lang_dir = self.base_dir / folder
            lang_dir.mkdir(parents=True, exist_ok=True)

            files = item.get("files") or {}
            key_map = {
                "whitepaper": "whitepaper",
                "master_library": "master_library",
                "mapping_rules": "mapping_rules",
                "translation_history": "translation_history",
            }
            for old_key, new_key in key_map.items():
                src = (files.get(old_key) or "").strip()
                if not src:
                    continue
                p = Path(src)
                if p.is_file():
                    shutil.copy2(p, self.asset_path(record, new_key))
            languages_out.append(record)

        if not languages_out:
            lang = self._bootstrap_language("默认语言")
            self._init_language_package(lang)
            languages_out = [lang]
        else:
            for record in languages_out:
                self._init_language_package(record)

        return {"project_name": project_name, "languages": languages_out}

    def rename_language(
        self,
        language: Dict[str, Any],
        new_display_name: str,
        all_languages: List[Dict[str, Any]],
    ) -> None:
        stripped = (new_display_name or "").strip()
        if not stripped:
            stripped = str(language.get("name") or "语言")
        new_name = self.ensure_unique_language_name(
            stripped, [x for x in all_languages if x["id"] != language["id"]]
        )
        old_folder = language["folder"]
        new_folder = self.ensure_unique_folder_name(new_name, exclude=old_folder)

        old_path = self.base_dir / old_folder
        new_path = self.base_dir / new_folder
        if old_path.exists() and old_path.resolve() != new_path.resolve():
            if new_path.exists():
                raise OSError(f"目标资料夹已存在：{new_folder}")
            old_path.rename(new_path)
        elif not old_path.exists():
            new_path.mkdir(parents=True, exist_ok=True)

        language["name"] = new_name
        language["folder"] = new_folder

    def delete_language_files(self, language: Dict[str, Any]) -> None:
        lang_dir = self.language_dir(language)
        if lang_dir.is_dir():
            shutil.rmtree(lang_dir, ignore_errors=False)
