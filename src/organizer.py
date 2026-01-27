import json
import shutil
import subprocess
import os
from pathlib import Path
from typing import Dict, Optional, Callable, List
import logging
import sys
import io

if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('organizer.log', encoding='utf-8', errors='replace')
    ],
    force=True
)
logger = logging.getLogger(__name__)


class OrganizationStats:
    def __init__(self):
        self.total = 0
        self.organized = 0
        self.needs_review = 0
        self.errors = []
    
    def to_dict(self):
        return {
            'total': self.total,
            'organized': self.organized,
            'needs_review': self.needs_review,
            'errors': self.errors
        }


class ContentOrganizer:
    FOLDERS = [
        'SoundEffects',
        'Music',
        'VerticalVideos',
        'HorizontalVideos',
        'FinalizedVideos',
        'Videos',
        'Images',
        'GreenscreenEffects',
        'PremiereProjects',
        'Uncategorized',
        'Other'
    ]
    
    VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.m4v'}
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg'}
    PREMIERE_EXTS = {'.prproj', '.aep', '.mogrt'}
    
    NAMING_TAGS = {
        'SoundEffects': ['_sfx', '_soundeffect', '_sound'],
        'Music': ['_music', '_song', '_audio'],
        'VerticalVideos': ['_vertical', '_vert', '_9x16'],
        'HorizontalVideos': ['_horizontal', '_horiz', '_16x9'],
        'GreenscreenEffects': ['_greenscreen', '_green', '_chroma'],
        'PremiereProjects': ['_premiere', '_project']
    }
    
    def __init__(self):
        self.stats = OrganizationStats()
        self._ffmpeg_available = None
    
    @property
    def ffmpeg_available(self):
        if self._ffmpeg_available is None:
            self._ffmpeg_available = self._check_ffmpeg()
        return self._ffmpeg_available
    
    def recheck_ffmpeg(self):
        self._ffmpeg_available = None
        result = self.ffmpeg_available
        logger.info(f"FFmpeg rechecked: {result}")
        return result
    
    def _check_ffmpeg(self):
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5,
                check=True
            )
            logger.info("FFmpeg detected in PATH")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        ffmpeg_dir = Path.cwd() / "ffmpeg"
        if ffmpeg_dir.exists():
            for root, dirs, files in os.walk(ffmpeg_dir):
                if 'ffmpeg.exe' in files or 'ffmpeg' in files:
                    ffmpeg_path = Path(root)
                    os.environ['PATH'] = str(ffmpeg_path) + os.pathsep + os.environ.get('PATH', '')
                    logger.info(f"FFmpeg found at {ffmpeg_path}")
                    return True
        
        logger.warning("FFmpeg not found")
        return False
    
    def _get_video_metadata(self, file_path: Path):
        if not self.ffmpeg_available:
            logger.debug(f"FFmpeg not available for {file_path.name}")
            return None
        
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-show_format',
                str(file_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10,
                check=False
            )
            
            if result.returncode != 0:
                logger.warning(f"ffprobe failed for {file_path.name}: {result.stderr}")
                return None
            
            if not result.stdout or result.stdout.strip() == '':
                logger.warning(f"ffprobe returned empty output for {file_path.name}")
                return None
            
            metadata = json.loads(result.stdout)
            return metadata
            
        except subprocess.TimeoutExpired:
            logger.warning(f"ffprobe timeout for {file_path.name}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse ffprobe output for {file_path.name}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error analyzing {file_path.name}: {e}")
            return None
    
    def _get_aspect_ratio(self, metadata: Dict):
        if not metadata or 'streams' not in metadata:
            logger.warning(f"No metadata or streams in metadata: {metadata}")
            return None
        
        for stream in metadata['streams']:
            if stream.get('codec_type') == 'video':
                width = stream.get('width')
                height = stream.get('height')
                
                logger.info(f"Video dimensions: {width}x{height}")
                
                if width and height:
                    aspect = 'vertical' if height > width else 'horizontal'
                    logger.info(f"Determined aspect: {aspect}")
                    return aspect
                else:
                    logger.warning(f"Missing width or height in stream: {stream}")
        
        logger.warning("No video stream found in metadata")
        return None
    
    def _get_duration(self, metadata: Dict):
        if not metadata:
            return None
        
        if 'format' in metadata and 'duration' in metadata['format']:
            try:
                return float(metadata['format']['duration'])
            except (ValueError, TypeError):
                pass
        
        for stream in metadata.get('streams', []):
            if stream.get('codec_type') == 'video' and 'duration' in stream:
                try:
                    return float(stream['duration'])
                except (ValueError, TypeError):
                    pass
        
        return None
    
    def detect_category_from_name(self, filename: str):
        lower_name = filename.lower()
        for category, tags in self.NAMING_TAGS.items():
            if any(tag in lower_name for tag in tags):
                return category
        return None
    
    def _clean_filename(self, filename: str):
        name = Path(filename).stem
        ext = Path(filename).suffix
        
        for tags in self.NAMING_TAGS.values():
            for tag in tags:
                name = name.replace(tag, '')
        
        name = name.replace('_', ' ').replace('-', ' ')
        name = ' '.join(name.split())
        
        return f"{name}{ext}"
    
    def categorize_file(self, file_path: Path, use_ffmpeg: bool = True):
        ext = file_path.suffix.lower()
        filename = file_path.name
        
        category = self.detect_category_from_name(filename)
        if category:
            return category
        
        if ext in self.PREMIERE_EXTS:
            return 'PremiereProjects'
        
        if ext in self.AUDIO_EXTS:
            return 'Uncategorized'
        
        if ext in self.IMAGE_EXTS:
            return 'Images'
        
        if ext in self.VIDEO_EXTS:
            if use_ffmpeg and self.ffmpeg_available:
                logger.info(f"Analyzing video: {filename}")
                metadata = self._get_video_metadata(file_path)
                
                if metadata:
                    aspect = self._get_aspect_ratio(metadata)
                    logger.info(f"Video {filename} aspect ratio: {aspect}")
                    
                    if aspect == 'vertical':
                        logger.info(f"Categorizing {filename} as VerticalVideos")
                        return 'VerticalVideos'
                    elif aspect == 'horizontal':
                        logger.info(f"Categorizing {filename} as HorizontalVideos")
                        return 'HorizontalVideos'
                    else:
                        logger.warning(f"Could not determine aspect ratio for {filename}, defaulting to Videos")
                else:
                    logger.warning(f"FFmpeg metadata extraction failed for {filename}, placing in Videos/")
            else:
                logger.info(f"FFmpeg disabled or unavailable for {filename}, placing in Videos/")
            
            return 'Videos'
        
        return 'Other'
    
    def create_folder_structure(self, output_path: Path):
        folders = {}
        
        for folder_name in self.FOLDERS:
            folder_path = output_path / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
            folders[folder_name] = folder_path
        
        logger.info(f"Created folder structure at {output_path}")
        return folders
    
    def organize_files(
        self,
        source_path: Path,
        output_path: Path,
        use_ffmpeg: bool = True,
        clean_filenames: bool = False,
        progress_callback: Optional[Callable[[float, str, str], None]] = None,
        organize_by_date: bool = True
    ):
        from datetime import datetime
        
        self.stats = OrganizationStats()
        folders = self.create_folder_structure(output_path)
        
        all_files = []
        for root, dirs, files in os.walk(source_path):
            for file in files:
                all_files.append(Path(root) / file)
        
        self.stats.total = len(all_files)
        logger.info(f"Found {self.stats.total} files to organize")
        
        for i, file_path in enumerate(all_files):
            try:
                category = self.categorize_file(file_path, use_ffmpeg)
                destination_folder = folders[category]
                
                if organize_by_date and category in ['VerticalVideos', 'HorizontalVideos', 'Clips', 'Videos']:
                    mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    year = mod_time.strftime("%Y")
                    month = mod_time.strftime("%B")
                    
                    destination_folder = destination_folder / year / month
                    destination_folder.mkdir(parents=True, exist_ok=True)
                
                filename = file_path.name
                if clean_filenames:
                    filename = self._clean_filename(filename)
                
                destination_path = destination_folder / filename
                counter = 1
                while destination_path.exists():
                    stem = Path(filename).stem
                    ext = Path(filename).suffix
                    destination_path = destination_folder / f"{stem}_{counter}{ext}"
                    counter += 1
                
                shutil.move(str(file_path), destination_path)
                self.stats.organized += 1
                
                if category == 'Uncategorized':
                    self.stats.needs_review += 1
                
                if progress_callback:
                    progress = (i + 1) / self.stats.total
                    display_category = category
                    if organize_by_date and category in ['VerticalVideos', 'HorizontalVideos', 'Clips', 'Videos']:
                        display_category = f"{category}/{year}/{month}"
                    progress_callback(progress, file_path.name, display_category)
                
                logger.debug(f"Moved {file_path.name} -> {category}/")
                
            except Exception as e:
                error_msg = f"{file_path.name}: {str(e)}"
                self.stats.errors.append(error_msg)
                logger.error(f"Failed to organize {file_path.name}: {e}")
        
        logger.info(f"Organization complete: {self.stats.organized}/{self.stats.total} files")
        return self.stats
