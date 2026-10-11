import os
import re
import shutil
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("pt_agent.organizer")

VIDEO_EXTS = {".mkv", ".mp4", ".ts", ".m2ts", ".avi", ".mov", ".wmv", ".iso"}
MIN_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB

class MediaOrganizer:
    """Hardlink and directory organizer for fnOS Media Center"""
    def __init__(self, media_root: str = "/vol1/1000/Media"):
        self.media_root = media_root

    def parse_title_and_year(self, name: str) -> Dict[str, Optional[str]]:
        """Extract title and year from release name"""
        # Match standard year 19xx or 20xx
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', ' ', name)
        m = re.search(r'[\s._\-](19\d\d|20\d\d)[\s._\-]', clean_name)
        if m:
            year = m.group(1)
            raw_title = clean_name[:m.start()].replace(".", " ").replace("_", " ").strip()
            # Clean Chinese / English separators
            raw_title = re.sub(r'\s+', ' ', raw_title)
            return {"title": raw_title, "year": year}
        
        # Fallback if year not found
        raw_title = name.replace(".", " ").replace("_", " ").strip()
        return {"title": raw_title, "year": None}

    def hardlink_file(self, src_path: str, dst_path: str) -> bool:
        """Create a hardlink, fallback to copy if cross-device"""
        try:
            target_dir = os.path.dirname(dst_path)
            os.makedirs(target_dir, exist_ok=True)
            try:
                os.chmod(target_dir, 0o775)
            except Exception:
                pass
            if os.path.exists(dst_path):
                logger.info(f"Target already exists, skipping: {dst_path}")
                return True
            os.link(src_path, dst_path)
            try:
                os.chmod(dst_path, 0o775)
            except Exception:
                pass
            logger.info(f"Hardlinked {src_path} -> {dst_path}")
            return True
        except OSError as e:
            logger.warning(f"Hardlink failed ({e}), attempting copy...")
            try:
                shutil.copy2(src_path, dst_path)
                return True
            except Exception as ce:
                logger.error(f"Copy also failed: {ce}")
                return False

    def organize_path(self, source_path: str, category: str = "外语电影", custom_title: Optional[str] = None) -> List[Dict[str, str]]:
        """Organize a downloaded file or directory into fnOS Media directory"""
        organized = []
        if not os.path.exists(source_path):
            logger.error(f"Source path does not exist: {source_path}")
            return []

        # Target category directory
        cat_dir = os.path.join(self.media_root, category)

        if os.path.isfile(source_path):
            files = [source_path]
        else:
            files = []
            for root, _, filenames in os.walk(source_path):
                for f in filenames:
                    files.append(os.path.join(root, f))

        for fpath in files:
            ext = os.path.splitext(fpath)[1].lower()
            if ext not in VIDEO_EXTS:
                continue

            try:
                if os.path.getsize(fpath) < MIN_VIDEO_SIZE:
                    continue
            except OSError:
                continue

            fname = os.path.basename(fpath)
            if custom_title:
                folder_name = custom_title
            else:
                info = self.parse_title_and_year(os.path.basename(source_path) if os.path.isdir(source_path) else fname)
                title = info["title"]
                year = info["year"]
                folder_name = f"{title} ({year})" if year else title

            target_folder = os.path.join(cat_dir, folder_name)
            target_file = os.path.join(target_folder, fname)

            if self.hardlink_file(fpath, target_file):
                organized.append({"source": fpath, "destination": target_file})

        return organized
