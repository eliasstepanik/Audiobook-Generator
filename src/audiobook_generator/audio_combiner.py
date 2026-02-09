"""Audio combination and post-processing for audiobooks."""

from pathlib import Path
from typing import List, Optional
import logging
from pydub import AudioSegment
from pydub.effects import normalize
import numpy as np

logger = logging.getLogger(__name__)


class AudioCombiner:
    """Combines multiple audio segments into a single file."""

    def __init__(
        self,
        silence_between_segments: int = 500,
        normalize_audio: bool = True,
        target_format: str = "mp3",
        bitrate: str = "192k",
    ):
        """
        Initialize audio combiner.

        Args:
            silence_between_segments: Milliseconds of silence between segments
            normalize_audio: Whether to normalize volume levels
            target_format: Output format (mp3, wav, etc.)
            bitrate: Target bitrate for compressed formats
        """
        self.silence_between_segments = silence_between_segments
        self.normalize_audio = normalize_audio
        self.target_format = target_format
        self.bitrate = bitrate

        logger.info(
            f"Initialized AudioCombiner: "
            f"format={target_format}, bitrate={bitrate}, "
            f"silence={silence_between_segments}ms"
        )

    def combine_wav_files(
        self, input_files: List[str], output_path: str, add_silence: bool = True
    ) -> str:
        """
        Combine multiple WAV files into a single audio file.

        Args:
            input_files: List of paths to input audio files
            output_path: Path for combined output file
            add_silence: Whether to add silence between segments

        Returns:
            Path to the combined audio file

        Raises:
            ValueError: If no input files provided
            FileNotFoundError: If input files don't exist
        """
        if not input_files:
            raise ValueError("No input files provided")

        logger.info(f"Combining {len(input_files)} audio files...")

        # Ensure output path has correct extension
        output_path = Path(output_path)
        if output_path.suffix != f".{self.target_format}":
            output_path = output_path.with_suffix(f".{self.target_format}")

        # Create silence segment if needed
        silence = None
        if add_silence and self.silence_between_segments > 0:
            silence = AudioSegment.silent(duration=self.silence_between_segments)

        # Load and combine audio segments
        combined = None

        for idx, file_path in enumerate(input_files):
            file_path = Path(file_path)

            if not file_path.exists():
                logger.warning(f"File not found, skipping: {file_path}")
                continue

            try:
                logger.info(
                    f"Loading segment {idx + 1}/{len(input_files)}: {file_path.name}"
                )

                # Load audio
                segment = AudioSegment.from_wav(str(file_path))

                # Normalize if enabled
                if self.normalize_audio:
                    segment = normalize(segment)

                # Add to combined audio
                if combined is None:
                    combined = segment
                else:
                    if silence:
                        combined += silence
                    combined += segment

            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                continue

        if combined is None:
            raise ValueError("No audio segments could be loaded")

        # Export combined audio
        logger.info(f"Exporting combined audio to: {output_path}")

        export_kwargs = {
            "format": self.target_format,
        }

        if self.target_format == "mp3":
            export_kwargs["bitrate"] = self.bitrate
            export_kwargs["parameters"] = ["-q:a", "2"]  # High quality VBR

        combined.export(str(output_path), **export_kwargs)

        duration_seconds = len(combined) / 1000
        logger.info(
            f"Combined audio created: {output_path} "
            f"(duration: {duration_seconds:.2f}s, size: {output_path.stat().st_size / 1024 / 1024:.2f}MB)"
        )

        return str(output_path)

    def combine_with_metadata(
        self,
        input_files: List[str],
        output_path: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        album: Optional[str] = None,
    ) -> str:
        """
        Combine audio files and add metadata tags.

        Args:
            input_files: List of paths to input audio files
            output_path: Path for combined output file
            title: Audio title
            author: Author/artist name
            album: Album name

        Returns:
            Path to the combined audio file
        """
        # First combine the audio
        combined_path = self.combine_wav_files(input_files, output_path)

        # Add metadata if format supports it
        if self.target_format == "mp3" and any([title, author, album]):
            try:
                from mutagen.mp3 import MP3
                from mutagen.id3 import ID3, TIT2, TPE1, TALB

                audio = MP3(combined_path, ID3=ID3)

                # Add ID3 tag if not exists
                try:
                    audio.add_tags()
                except Exception:
                    pass  # Tags may already exist

                if title:
                    audio.tags.add(TIT2(encoding=3, text=title))
                if author:
                    audio.tags.add(TPE1(encoding=3, text=author))
                if album:
                    audio.tags.add(TALB(encoding=3, text=album))

                audio.save()
                logger.info("Metadata added to audio file")

            except ImportError:
                logger.warning("mutagen not installed, skipping metadata")
            except Exception as e:
                logger.error(f"Error adding metadata: {e}")

        return combined_path

    def split_into_chapters(
        self,
        input_file: str,
        chapter_boundaries: List[int],
        output_dir: str,
        chapter_prefix: str = "chapter",
    ) -> List[str]:
        """
        Split combined audio into chapter files.

        Args:
            input_file: Path to combined audio file
            chapter_boundaries: List of segment indices where chapters start
            output_dir: Directory for chapter files
            chapter_prefix: Prefix for chapter filenames

        Returns:
            List of paths to chapter files
        """
        logger.info(f"Splitting audio into {len(chapter_boundaries)} chapters...")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load full audio
        audio = AudioSegment.from_file(str(input_file))

        chapter_files = []

        for idx, start_ms in enumerate(chapter_boundaries):
            end_ms = (
                chapter_boundaries[idx + 1]
                if idx + 1 < len(chapter_boundaries)
                else len(audio)
            )

            chapter = audio[start_ms:end_ms]

            chapter_path = (
                output_dir / f"{chapter_prefix}_{idx + 1:03d}.{self.target_format}"
            )

            chapter.export(
                str(chapter_path),
                format=self.target_format,
                bitrate=self.bitrate if self.target_format == "mp3" else None,
            )

            chapter_files.append(str(chapter_path))
            logger.info(f"Created chapter {idx + 1}: {chapter_path.name}")

        return chapter_files
