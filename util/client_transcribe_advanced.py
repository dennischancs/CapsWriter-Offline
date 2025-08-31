import os
import subprocess
import srt
import chardet
import asyncio
import uuid
from pathlib import Path
from typing import List, Tuple, Optional

from config import ClientConfig as Config
from util.client_transcribe import transcribe_check, transcribe_send, transcribe_recv
from util.client_cosmic import console, Cosmic

# Helper to get media duration using ffprobe
def get_media_duration_ffprobe(file_path: Path) -> Optional[float]:
    try:
        command = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{file_path}"'
        duration_str = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT).decode().strip()
        return float(duration_str)
    except Exception as e:
        console.print(f"[bold red]Error getting media duration for {file_path}: {e}[/bold red]")
        return None

# Helper to extract audio using the configured FFmpeg command
def extract_audio_with_ffmpeg(input_media_path: Path, output_audio_path: Path) -> bool:
    cmd = []
    for part in Config.FFMPEG_AUDIO_EXTRACTION_CMD_TEMPLATE:
        if part == "{input_file}":
            cmd.append(str(input_media_path))
        elif part == "{output_file}":
            cmd.append(str(output_audio_path))
        else:
            cmd.append(part)

    console.print(f"Extracting audio to: {output_audio_path}")
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            console.print(f"[bold red]FFmpeg audio extraction failed for {input_media_path}[/bold red]")
            console.print(f"[bold red]FFmpeg stderr:[/bold red]\n{stderr.decode(errors='ignore')}")
            return False
        return True
    except Exception as e:
        console.print(f"[bold red]Exception during FFmpeg audio extraction for {input_media_path}: {e}[/bold red]")
        return False

# Helper to split audio using ffmpeg
def split_audio_ffmpeg(audio_path: Path, split_duration_seconds: int) -> Optional[List[Path]]:
    """
    Split audio file using FFmpeg for better performance and cross-platform compatibility.
    
    Args:
        audio_path: Path to the input audio file
        split_duration_seconds: Duration in seconds for each chunk
        
    Returns:
        List of paths to the split audio chunks, or None if failed
    """
    try:
        # Get audio duration using ffprobe
        duration = get_media_duration_ffprobe(audio_path)
        if duration is None:
            console.print(f"[bold red]Could not get duration for {audio_path}[/bold red]")
            return None
            
        if duration <= split_duration_seconds:
            return [audio_path]  # No splitting needed

        # Calculate number of chunks, avoiding tiny final chunks
        import math
        num_full_chunks = math.floor(duration / split_duration_seconds)
        remainder = duration % split_duration_seconds
        # Add an extra chunk for the remainder only if it's significant (e.g., > 0.1s)
        num_splits = num_full_chunks + (1 if remainder > 0.1 else 0)
        # Ensure at least one chunk if the file is not empty
        if num_splits == 0 and duration > 0:
            num_splits = 1
        base_name = audio_path.stem
        output_dir = audio_path.parent
        chunk_paths = []

        console.print(f"Splitting audio into {num_splits} chunks using FFmpeg...")

        # Generate FFmpeg segmentation command
        # Create a temporary segment list file for more precise control
        segment_list_path = output_dir / f"{base_name}_segments.txt"
        
        try:
            # Write segment list
            with open(segment_list_path, 'w', encoding='utf-8') as f:
                for i in range(num_splits):
                    start_time = i * split_duration_seconds
                    end_time = min((i + 1) * split_duration_seconds, duration)
                    duration_chunk = end_time - start_time
                    
                    chunk_filename = f"{base_name}{Config.SPLIT_AUDIO_SUFFIX_PREFIX}{i}{audio_path.suffix}"
                    chunk_path = output_dir / chunk_filename
                    chunk_paths.append(chunk_path)
                    
                    # Write segment entry: out_filename start_time duration
                    f.write(f"{chunk_filename} {start_time:.3f} {duration_chunk:.3f}\n")

            # Use FFmpeg with segment demuxer
            cmd = [
                "ffmpeg",
                "-i", str(audio_path),  # Input file
                "-f", "segment",        # Use segment demuxer
                "-segment_list", str(segment_list_path),  # Segment list file
                "-segment_times", ",".join([str(i * split_duration_seconds) for i in range(1, num_splits)]),  # Split points
                "-segment_time_delta", "0.001",  # Small delta to ensure proper splitting
                "-acodec", "pcm_s16le",  # Audio codec (same as extraction)
                "-ar", "16000",         # Sample rate (consistent with transcription)
                "-ac", "1",             # Mono channel
                "-y",                   # Overwrite output files
                str(output_dir / f"{base_name}{Config.SPLIT_AUDIO_SUFFIX_PREFIX}%d{audio_path.suffix}")
            ]

            console.print(f"Executing FFmpeg split command: {' '.join(cmd)}")
            
            # Run FFmpeg
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                console.print(f"[bold red]FFmpeg audio splitting failed for {audio_path}[/bold red]")
                console.print(f"[bold red]FFmpeg stderr:[/bold red]\n{stderr.decode(errors='ignore')}")
                return None

            # Verify that all expected chunk files were created
            existing_chunks = []
            for chunk_path in chunk_paths:
                if chunk_path.exists():
                    existing_chunks.append(chunk_path)
                else:
                    console.print(f"[yellow]Warning: Expected chunk {chunk_path.name} was not created[/yellow]")
            
            if not existing_chunks:
                console.print(f"[bold red]No audio chunks were created for {audio_path}[/bold red]")
                return None
                
            console.print(f"Successfully created {len(existing_chunks)} audio chunks")
            return existing_chunks

        finally:
            # Clean up segment list file
            if segment_list_path.exists():
                try:
                    segment_list_path.unlink()
                except OSError as e:
                    console.print(f"[yellow]Warning: Could not delete segment list file {segment_list_path}: {e}[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error splitting audio {audio_path} with FFmpeg: {e}[/bold red]")
        return None

# Helper to split audio directly from media file using ffmpeg
def split_media_audio_ffmpeg(media_path: Path, split_duration_seconds: int) -> Optional[List[Path]]:
    """
    Split audio directly from media file (video or audio) using FFmpeg.
    This avoids the intermediate step of extracting audio to a separate WAV file.
    
    Args:
        media_path: Path to the input media file (video or audio)
        split_duration_seconds: Duration in seconds for each chunk
        
    Returns:
        List of paths to the split audio chunks, or None if failed
    """
    try:
        # Get media duration using ffprobe
        duration = get_media_duration_ffprobe(media_path)
        if duration is None:
            console.print(f"[bold red]Could not get duration for {media_path}[/bold red]")
            return None
            
        if duration <= split_duration_seconds:
            # For short files, extract the entire audio as a single chunk
            base_name = media_path.stem
            output_dir = media_path.parent
            single_chunk_path = output_dir / f"{base_name}{Config.TEMP_AUDIO_SUFFIX}"
            
            # Extract audio for the single chunk
            if extract_audio_with_ffmpeg(media_path, single_chunk_path):
                return [single_chunk_path]
            else:
                return None

        # Calculate number of chunks, avoiding tiny final chunks
        import math
        num_full_chunks = math.floor(duration / split_duration_seconds)
        remainder = duration % split_duration_seconds
        # Add an extra chunk for the remainder only if it's significant (e.g., > 0.1s)
        num_splits = num_full_chunks + (1 if remainder > 0.1 else 0)
        # Ensure at least one chunk if the file is not empty
        if num_splits == 0 and duration > 0:
            num_splits = 1
        base_name = media_path.stem
        output_dir = media_path.parent
        chunk_paths = []

        console.print(f"Splitting media audio directly into {num_splits} chunks using FFmpeg...")

        # Generate FFmpeg segmentation command for direct media splitting
        # Use segment demuxer with audio stream selection
        cmd = [
            "ffmpeg",
            "-i", str(media_path),  # Input media file
            "-vn",                 # No video
            "-acodec", "pcm_s16le",  # Audio codec (same as extraction)
            "-ar", "16000",         # Sample rate (consistent with transcription)
            "-ac", "1",             # Mono channel
            "-async", "1",         # Resync audio
            "-f", "segment",        # Use segment demuxer
            "-segment_times", ",".join([str(i * split_duration_seconds) for i in range(1, num_splits)]),  # Split points
            "-segment_time_delta", "0.001",  # Small delta to ensure proper splitting
            "-y",                   # Overwrite output files
            str(output_dir / f"{base_name}{Config.SPLIT_AUDIO_SUFFIX_PREFIX}%d.wav")
        ]

        console.print(f"Executing FFmpeg direct media split command: {' '.join(cmd)}")
        
        # Run FFmpeg
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            console.print(f"[bold red]FFmpeg direct media splitting failed for {media_path}[/bold red]")
            console.print(f"[bold red]FFmpeg stderr:[/bold red]\n{stderr.decode(errors='ignore')}")
            return None

        # Verify chunk files were created and build the list
        existing_chunks = []
        for i in range(num_splits):
            chunk_filename = f"{base_name}{Config.SPLIT_AUDIO_SUFFIX_PREFIX}{i}.wav"
            chunk_path = output_dir / chunk_filename
            if chunk_path.exists():
                existing_chunks.append(chunk_path)
            else:
                console.print(f"[yellow]Warning: Expected chunk {chunk_filename} was not created[/yellow]")
        
        if not existing_chunks:
            console.print(f"[bold red]No audio chunks were created for {media_path}[/bold red]")
            return None
            
        console.print(f"Successfully created {len(existing_chunks)} audio chunks")
        return existing_chunks

    except Exception as e:
        console.print(f"[bold red]Error splitting media audio {media_path} with FFmpeg: {e}[/bold red]")
        return None

# Helper to transcribe a single audio chunk using existing logic
async def transcribe_audio_chunk(chunk_path: Path, original_task_id_base: str, chunk_index: int) -> Optional[Tuple[Path, Path]]:
    chunk_task_id = f"{original_task_id_base}_{chunk_index}" # For logging, actual task_id is generated by transcribe_send
    console.print(f"  Transcribing chunk {chunk_index} ({chunk_path.name})")

    try:
        await transcribe_check(chunk_path) # Check connection and file existence for this specific chunk
        if not Cosmic.websocket:
             console.print(f"[bold red]Cannot connect to server for chunk {chunk_path.name}. Aborting this chunk.[/bold red]")
             return None

        await transcribe_send(chunk_path)
        await transcribe_recv(chunk_path) # This function writes the .txt, .json, .merge.txt, .srt files

        # transcribe_recv writes files with the same base name as chunk_path
        txt_file = chunk_path.with_suffix(".txt")
        srt_file = chunk_path.with_suffix(".srt")
        
        if txt_file.exists() and srt_file.exists():
            return txt_file, srt_file
        else:
            console.print(f"[bold red]Transcription of chunk {chunk_path.name} did not produce expected output files.[/bold red]")
            return None
    except Exception as e:
        console.print(f"[bold red]Error transcribing chunk {chunk_path.name}: {e}[/bold red]")
        return None
    finally:
        if Cosmic.websocket:
            await Cosmic.websocket.close()
            console.print(f"  Closed WebSocket connection for chunk {chunk_path.name}")

# Helper to merge TXT files (adapted from media2srt.py)
def merge_txt_files(original_file_path: Path, chunk_txt_paths: List[Path]) -> Optional[Path]:
    if not chunk_txt_paths:
        return None
    
    merged_content = ""
    for txt_path in sorted(chunk_txt_paths): # Sort to ensure order
        try:
            with open(txt_path, 'rb') as f:
                raw_data = f.read()
                detected_encoding = chardet.detect(raw_data)['encoding']
                content = raw_data.decode(detected_encoding if detected_encoding else 'utf-8')
                merged_content += content + "\n"
        except Exception as e:
            console.print(f"[bold red]Error reading chunk TXT {txt_path}: {e}[/bold red]")
            return None
    
    final_txt_path = original_file_path.with_suffix(".txt")
    try:
        with open(final_txt_path, 'w', encoding='utf-8') as f:
            f.write(merged_content)
        console.print(f"Merged TXT file created: {final_txt_path}")
        return final_txt_path
    except Exception as e:
        console.print(f"[bold red]Error writing merged TXT {final_txt_path}: {e}[/bold red]")
        return None

# Helper to correct and merge SRT files (adapted from media2srt.py)
def correct_and_merge_srt_files(original_file_path: Path, chunk_srt_paths: List[Path]) -> Optional[Path]:
    if not chunk_srt_paths:
        return None

    merged_subtitles = []
    current_time_offset = 0.0

    for srt_path in sorted(chunk_srt_paths): # Sort to ensure order
        try:
            with open(srt_path, 'rb') as f:
                raw_data = f.read()
                detected_encoding = chardet.detect(raw_data)['encoding']
                content = raw_data.decode(detected_encoding if detected_encoding else 'utf-8')
                subtitles = list(srt.parse(content))

            if not subtitles:
                continue

            # Calculate duration of this chunk to update the offset for the next one
            # Use the end time of the last subtitle in the chunk
            last_subtitle_end_time = subtitles[-1].end.total_seconds()
            
            for subtitle in subtitles:
                # Apply time offset
                subtitle.start = srt.timedelta(seconds=subtitle.start.total_seconds() + current_time_offset)
                subtitle.end = srt.timedelta(seconds=subtitle.end.total_seconds() + current_time_offset)
                subtitle.index = len(merged_subtitles) + 1 # Re-index
                merged_subtitles.append(subtitle)
            
            current_time_offset += last_subtitle_end_time

        except Exception as e:
            console.print(f"[bold red]Error processing/correcting chunk SRT {srt_path}: {e}[/bold red]")
            return None
    
    final_srt_path = original_file_path.with_suffix(".srt")
    try:
        with open(final_srt_path, 'w', encoding='utf-8') as f:
            f.write(srt.compose(merged_subtitles))
        console.print(f"Merged and corrected SRT file created: {final_srt_path}")
        return final_srt_path
    except Exception as e:
        console.print(f"[bold red]Error writing merged SRT {final_srt_path}: {e}[/bold red]")
        return None

# Helper to clean up intermediate files based on their stems
def cleanup_intermediate_files_by_stems(stems_to_remove: List[str], original_file_path: Path):
    if not stems_to_remove:
        console.print("[yellow]No stems to clean up[/yellow]")
        return
        
    console.print(f"[cyan]Starting cleanup of {len(stems_to_remove)} stem(s)[/cyan]")
    console.print(f"[cyan]Stems to clean: {stems_to_remove}[/cyan]")
    console.print(f"[cyan]Original file path: {original_file_path}[/cyan]")
    
    # Define the suffixes of files to be removed
    suffixes_to_remove = [".wav", ".txt", ".srt", ".json", ".merge.txt"]
    total_cleaned = 0
    total_errors = 0
    
    # Use the original file's directory for cleanup
    directory = original_file_path.parent
    console.print(f"[cyan]Cleaning in directory: {directory}[/cyan]")
    
    # First, let's check what files actually exist in the directory
    console.print(f"[cyan]Files in directory:[/cyan]")
    for file in directory.iterdir():
        if any(file.name.endswith(suffix) for suffix in suffixes_to_remove):
            console.print(f"    Found: {file}")
    
    for stem_str in stems_to_remove:
        console.print(f"  Cleaning up stem: {stem_str}")
        stem_cleaned = 0
        stem_errors = 0
        
        # stem_str is already the stem name, use it directly
        stem_name = stem_str
        
        console.print(f"    Stem name: {stem_name}")
        
        for suffix in suffixes_to_remove:
            # Construct the full file path using the original file's directory and stem name
            file_to_remove = directory / f"{stem_name}{suffix}"
            console.print(f"    Looking for: {file_to_remove}")
            try:
                if file_to_remove.exists():
                    os.remove(file_to_remove)
                    console.print(f"    ✓ Cleaned up: {file_to_remove}")
                    stem_cleaned += 1
                    total_cleaned += 1
                else:
                    console.print(f"    - File not found: {file_to_remove}")
            except OSError as e:
                console.print(f"[yellow]    ✗ Error deleting {file_to_remove}: {e}[/yellow]")
                stem_errors += 1
                total_errors += 1
        
        if stem_cleaned > 0:
            console.print(f"  → Stem {stem_str}: {stem_cleaned} files cleaned, {stem_errors} errors")
        elif stem_errors == 0:
            console.print(f"  → Stem {stem_str}: no files found (already clean)")
    
    console.print(f"[green]Cleanup completed: {total_cleaned} files cleaned, {total_errors} errors[/green]")
    
    # Additional cleanup: Look for any remaining chunk files with the split pattern
    try:
        # Use the original file name as base for pattern matching
        base_name = original_file_path.stem
        
        # Look for files that match the split pattern
        split_pattern = f"{base_name}{Config.SPLIT_AUDIO_SUFFIX_PREFIX}"
        console.print(f"[cyan]Checking for additional split files with pattern: {split_pattern}*[/cyan]")
        
        additional_cleaned = 0
        for file in directory.glob(f"{split_pattern}*"):
            if any(file.name.endswith(suffix) for suffix in suffixes_to_remove):
                try:
                    file.unlink()
                    console.print(f"    ✓ Additional cleanup: {file}")
                    additional_cleaned += 1
                except OSError as e:
                    console.print(f"[yellow]    ✗ Error deleting {file}: {e}[/yellow]")
        
        if additional_cleaned > 0:
            console.print(f"[green]Additional cleanup: {additional_cleaned} more files cleaned[/green]")
    except Exception as e:
        console.print(f"[yellow]Error during additional cleanup: {e}[/yellow]")

# Helper to clean up existing temp audio files before starting a new transcription
def cleanup_existing_temp_files(file_path: Path):
    """
    Clean up any existing temp audio files that might be left from interrupted tasks.
    This prevents processing old temp files instead of the intended media file.
    """
    console.print(f"[cyan][Cleanup] Checking for existing temp files before processing: {file_path}[/cyan]")
    
    # Get the directory and base name of the original file
    directory = file_path.parent
    base_name = file_path.stem
    
    # Define the temp audio file pattern to look for
    temp_audio_patterns = [
        f"{base_name}{Config.TEMP_AUDIO_SUFFIX}",  # Original temp file pattern
        f"{base_name}_temp_audio_temp_audio.wav",  # Nested temp file pattern (the problematic case)
    ]
    
    cleaned_count = 0
    error_count = 0
    
    for temp_pattern in temp_audio_patterns:
        temp_file_path = directory / temp_pattern
        try:
            if temp_file_path.exists():
                console.print(f"[yellow]Found existing temp file: {temp_file_path}[/yellow]")
                os.remove(temp_file_path)
                console.print(f"[green]✓ Removed existing temp file: {temp_file_path}[/green]")
                cleaned_count += 1
            else:
                console.print(f"[dim]No temp file found at: {temp_file_path}[/dim]")
        except OSError as e:
            console.print(f"[bold red]✗ Error removing temp file {temp_file_path}: {e}[/bold red]")
            error_count += 1
    
    # Also check for any other problematic temp files that might have been created
    # Look for files that start with the temp audio pattern
    try:
        temp_prefix = f"{base_name}{Config.TEMP_AUDIO_SUFFIX}"
        for temp_file in directory.glob(f"{temp_prefix}*"):
            if temp_file.name != Config.TEMP_AUDIO_SUFFIX.lstrip("_"):  # Avoid removing unrelated temp files
                try:
                    console.print(f"[yellow]Found additional temp-related file: {temp_file}[/yellow]")
                    os.remove(temp_file)
                    console.print(f"[green]✓ Removed additional temp file: {temp_file}[/green]")
                    cleaned_count += 1
                except OSError as e:
                    console.print(f"[bold red]✗ Error removing additional temp file {temp_file}: {e}[/bold red]")
                    error_count += 1
    except Exception as e:
        console.print(f"[yellow]Error during additional temp file cleanup: {e}[/yellow]")
    
    if cleaned_count > 0:
        console.print(f"[green][Cleanup] Successfully removed {cleaned_count} temp file(s)[/green]")
    elif error_count == 0:
        console.print(f"[dim][Cleanup] No existing temp files found[/dim]")
    
    if error_count > 0:
        console.print(f"[bold red][Cleanup] {error_count} error(s) occurred during cleanup[/bold red]")

# Main function to process a media file
async def process_media_file(file_path: Path):
    console.print(f"\n[cyan][Process Media File] Starting for: {file_path}[/cyan]")
    
    # Clean up any existing temp files before starting
    cleanup_existing_temp_files(file_path)
    
    final_srt_path = file_path.with_suffix(".srt")
    final_txt_path = file_path.with_suffix(".txt")

    if final_srt_path.exists() and final_txt_path.exists():
        console.print(f"[yellow]Skipping {file_path} as .srt and .txt already exist.[/yellow]")
        return

    base_task_id = str(uuid.uuid1())
    stems_to_cleanup = [] # Store stems for cleanup

    try:
        # Get media duration directly from the original file
        duration = get_media_duration_ffprobe(file_path)
        if duration is None:
            console.print(f"[bold red]Could not get duration for {file_path}[/bold red]")
            return
        
        console.print(f"Original media duration: {duration:.2f}s")

        # Direct audio splitting from media file (optimized path)
        audio_chunks_to_transcribe: List[Path] = []
        if duration > Config.SPLIT_DURATION_SECONDS:
            console.print(f"Duration exceeds split threshold ({Config.SPLIT_DURATION_SECONDS}s). Splitting audio directly from media.")
            split_chunks = split_media_audio_ffmpeg(file_path, Config.SPLIT_DURATION_SECONDS)
            if split_chunks:
                audio_chunks_to_transcribe.extend(split_chunks)
                # Add stems of split chunks for cleanup
                stems_to_cleanup.extend([p.stem for p in split_chunks])
            else:
                console.print(f"[bold red]Direct audio splitting failed for {file_path}[/bold red]")
                return
        else:
            console.print("Duration within threshold. Extracting audio as single chunk.")
            # For short files, extract the entire audio
            # Ensure temp audio file is created in the same directory as the original file
            temp_audio_path = file_path.parent / (file_path.stem + Config.TEMP_AUDIO_SUFFIX)
            stems_to_cleanup.append(temp_audio_path.stem)
            
            if not extract_audio_with_ffmpeg(file_path, temp_audio_path):
                console.print(f"[bold red]Audio extraction failed for {file_path}[/bold red]")
                return
            audio_chunks_to_transcribe.append(temp_audio_path)
        
        # Transcribe Chunks
        transcribed_chunk_txts: List[Path] = []
        transcribed_chunk_srts: List[Path] = []
        for i, chunk_path in enumerate(audio_chunks_to_transcribe):
            result = await transcribe_audio_chunk(chunk_path, base_task_id, i)
            if result:
                txt_file, srt_file = result
                transcribed_chunk_txts.append(txt_file)
                transcribed_chunk_srts.append(srt_file)
            else:
                console.print(f"[bold red]Failed to transcribe chunk {chunk_path.name}. Aborting merge for {file_path.name}.[/bold red]")
                cleanup_intermediate_files_by_stems(stems_to_cleanup, file_path)
                return
        
        # Merge Results
        if len(audio_chunks_to_transcribe) > 1: # Only merge if it was split
            if transcribed_chunk_txts:
                merge_txt_files(file_path, transcribed_chunk_txts)
            if transcribed_chunk_srts:
                correct_and_merge_srt_files(file_path, transcribed_chunk_srts)
            
            # After merging, add all intermediate chunk files to cleanup list
            for chunk_path in audio_chunks_to_transcribe:
                chunk_stem = chunk_path.stem
                if chunk_stem not in stems_to_cleanup:
                    stems_to_cleanup.append(chunk_stem)
            
            console.print(f"Added {len(audio_chunks_to_transcribe)} chunk stems to cleanup list")
        else: # Single chunk, just rename output files to final names
            if transcribed_chunk_txts:
                try:
                    os.rename(transcribed_chunk_txts[0], final_txt_path)
                    console.print(f"Renamed {transcribed_chunk_txts[0].name} to {final_txt_path.name}")
                except OSError as e:
                    console.print(f"[bold red]Error renaming TXT file: {e}[/bold red]")
            if transcribed_chunk_srts:
                try:
                    os.rename(transcribed_chunk_srts[0], final_srt_path)
                    console.print(f"Renamed {transcribed_chunk_srts[0].name} to {final_srt_path.name}")
                except OSError as e:
                    console.print(f"[bold red]Error renaming SRT file: {e}[/bold red]")
        
        console.print(f"[green][Process Media File] Successfully completed for: {file_path}[/green]")

    finally:
        # Cleanup
        cleanup_intermediate_files_by_stems(stems_to_cleanup, file_path)
