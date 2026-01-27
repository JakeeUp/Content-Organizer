"""
Utility functions for the content organizer.
Includes FFmpeg download with real progress reporting.
"""

import subprocess
import urllib.request
import zipfile
import platform
import os
from pathlib import Path
from typing import Optional, Callable
import logging
import time

logger = logging.getLogger(__name__)


def download_ffmpeg(install_dir: Optional[Path] = None) -> bool:
    """
    Download and install FFmpeg.
    
    Args:
        install_dir: Installation directory (default: ./ffmpeg)
        
    Returns:
        True if successful, False otherwise
    """
    system = platform.system()
    
    if install_dir is None:
        install_dir = Path.cwd() / "ffmpeg"
    
    install_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        if system == "Windows":
            logger.info("Downloading FFmpeg for Windows...")
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            zip_path = install_dir / "ffmpeg.zip"
            
            # Simple download (GUI polls file size for progress)
            urllib.request.urlretrieve(url, zip_path)
            
            logger.info("Download complete, extracting...")
            
            # Extract
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(install_dir)
            
            # Find ffmpeg.exe and add to PATH
            for root, dirs, files in os.walk(install_dir):
                if 'ffmpeg.exe' in files:
                    ffmpeg_path = Path(root)
                    os.environ['PATH'] = str(ffmpeg_path) + os.pathsep + os.environ.get('PATH', '')
                    logger.info(f"FFmpeg installed successfully at {ffmpeg_path}")
                    
                    # Clean up zip
                    try:
                        zip_path.unlink()
                    except:
                        pass
                    
                    return True
            
            logger.warning("Could not find ffmpeg.exe after extraction")
            return False
            
        else:
            logger.info(f"Please install FFmpeg manually on {system}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to download FFmpeg: {e}")
        return False


def validate_folder_path(path_str: str) -> Optional[Path]:
    """
    Validate and return a folder path.
    
    Args:
        path_str: Path string to validate
        
    Returns:
        Path object if valid, None otherwise
    """
    if not path_str:
        return None
    
    try:
        path = Path(path_str)
        if path.exists() and path.is_dir():
            return path
        return None
    except Exception:
        return None


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
