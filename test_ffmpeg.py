"""
Test if FFmpeg is actually working
"""

import subprocess
import sys
from pathlib import Path

print("=" * 60)
print("FFMPEG TEST SCRIPT")
print("=" * 60)

# Test 1: Check if ffmpeg exists
print("\n1. Testing if ffmpeg command exists...")
try:
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print("   ✅ FFmpeg found!")
        print(f"   Version: {result.stdout.split('\\n')[0]}")
    else:
        print("   ❌ FFmpeg command failed")
        sys.exit(1)
except FileNotFoundError:
    print("   ❌ FFmpeg not found in PATH")
    sys.exit(1)
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

# Test 2: Check if ffprobe exists
print("\n2. Testing if ffprobe command exists...")
try:
    result = subprocess.run(['ffprobe', '-version'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print("   ✅ FFprobe found!")
    else:
        print("   ❌ FFprobe command failed")
        sys.exit(1)
except FileNotFoundError:
    print("   ❌ FFprobe not found in PATH")
    sys.exit(1)
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

# Test 3: Analyze a real video file
print("\n3. Testing video analysis...")
print("   Enter path to a video file to test:")
video_path = input("   > ").strip().strip('"')

if not Path(video_path).exists():
    print(f"   ❌ File not found: {video_path}")
    sys.exit(1)

print(f"   Analyzing: {Path(video_path).name}")

try:
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        '-show_format',
        video_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode != 0:
        print(f"   ❌ FFprobe failed: {result.stderr}")
        sys.exit(1)
    
    import json
    metadata = json.loads(result.stdout)
    
    # Find video stream
    for stream in metadata.get('streams', []):
        if stream.get('codec_type') == 'video':
            width = stream.get('width')
            height = stream.get('height')
            
            print(f"\n   ✅ Video analyzed successfully!")
            print(f"   Resolution: {width}x{height}")
            
            if width and height:
                if height > width:
                    print(f"   Aspect: VERTICAL (height {height} > width {width})")
                else:
                    print(f"   Aspect: HORIZONTAL (width {width} >= height {height})")
            break
    else:
        print("   ❌ No video stream found in file")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED! FFmpeg is working correctly!")
print("=" * 60)
input("\nPress Enter to exit...")
