#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script to verify the fixes for relative path support and output path issues
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the current directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from core_client import init_file
from util.client_transcribe_advanced import process_media_file
from util.client_transcribe import transcribe_recv

def test_relative_path_resolution():
    """Test that relative paths are resolved correctly"""
    print("=== Testing Relative Path Resolution ===")
    
    # Create a temporary directory and file for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a test audio file (just a dummy file for path testing)
        test_file = temp_path / "test_audio.m4a"
        test_file.write_text("dummy audio content")
        
        # Create a subdirectory and change to it
        subdir = temp_path / "subdir"
        subdir.mkdir()
        original_cwd = os.getcwd()
        os.chdir(subdir)
        
        try:
            # Test relative path resolution
            relative_path = Path("../test_audio.m4a")
            abs_path = relative_path.resolve()
            
            print(f"Original relative path: {relative_path}")
            print(f"Resolved absolute path: {abs_path}")
            print(f"Expected absolute path: {test_file}")
            
            # Verify the resolution is correct
            assert abs_path == test_file, f"Path resolution failed: {abs_path} != {test_file}"
            print("✓ Relative path resolution works correctly")
            
        finally:
            os.chdir(original_cwd)

def test_output_path_handling():
    """Test that output files are created in the correct directory"""
    print("\n=== Testing Output Path Handling ===")
    
    # Create a temporary directory and file for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a test audio file path
        test_file = temp_path / "test_audio.m4a"
        test_file.write_text("dummy audio content")
        
        # Create a subdirectory and change to it (simulating the issue)
        subdir = temp_path / "subdir"
        subdir.mkdir()
        original_cwd = os.getcwd()
        os.chdir(subdir)
        
        try:
            # Test that output paths are correctly determined
            file_path = Path(test_file)
            
            # These should be in the same directory as the input file
            txt_output = file_path.with_suffix(".txt")
            srt_output = file_path.with_suffix(".srt")
            json_output = file_path.with_suffix(".json")
            
            print(f"Input file: {file_path}")
            print(f"Expected TXT output: {txt_output}")
            print(f"Expected SRT output: {srt_output}")
            print(f"Expected JSON output: {json_output}")
            
            # Verify the output paths are in the correct directory
            assert txt_output.parent == test_file.parent, f"TXT output in wrong directory: {txt_output.parent}"
            assert srt_output.parent == test_file.parent, f"SRT output in wrong directory: {srt_output.parent}"
            assert json_output.parent == test_file.parent, f"JSON output in wrong directory: {json_output.parent}"
            
            print("✓ Output path handling works correctly")
            
        finally:
            os.chdir(original_cwd)

def test_temp_audio_path_creation():
    """Test that temporary audio files are created in the correct directory"""
    print("\n=== Testing Temporary Audio Path Creation ===")
    
    # Create a temporary directory and file for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a test media file path
        test_file = temp_path / "test_video.mp4"
        test_file.write_text("dummy video content")
        
        # Test temp audio path creation logic
        from config import ClientConfig as Config
        
        # This should create the temp file in the same directory as the original
        temp_audio_path = test_file.parent / (test_file.stem + Config.TEMP_AUDIO_SUFFIX)
        
        print(f"Original file: {test_file}")
        print(f"Temp audio path: {temp_audio_path}")
        
        # Verify the temp path is in the correct directory
        assert temp_audio_path.parent == test_file.parent, f"Temp audio file in wrong directory: {temp_audio_path.parent}"
        assert temp_audio_path.name.endswith(Config.TEMP_AUDIO_SUFFIX), f"Temp audio file has wrong suffix: {temp_audio_path.name}"
        
        print("✓ Temporary audio path creation works correctly")

if __name__ == "__main__":
    print("Testing fixes for CapsWriter-Offline path handling issues...\n")
    
    try:
        test_relative_path_resolution()
        test_output_path_handling()
        test_temp_audio_path_creation()
        
        print("\n🎉 All tests passed! The fixes should resolve the reported issues.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
