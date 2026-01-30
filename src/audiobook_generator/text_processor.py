"""Text processing module for handling text files and batching."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import re


@dataclass
class TextBatch:
    """Represents a batch of text for processing."""

    text: str
    start_char: int
    end_char: int
    batch_index: int

    @property
    def length(self) -> int:
        """Return character length of the batch."""
        return len(self.text)


class TextProcessor:
    """Handles reading and batching text files for processing."""

    def __init__(self, max_chars: int = 16000):
        """
        Initialize text processor.

        Args:
            max_chars: Maximum characters per batch (default 16k for context)
        """
        self.max_chars = max_chars

    def read_file(self, file_path: str) -> str:
        """
        Read text file with automatic encoding detection.

        Args:
            file_path: Path to the text file

        Returns:
            Content of the file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file cannot be read
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Try common encodings
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

        for encoding in encodings:
            try:
                with open(path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue

        raise ValueError(f"Could not decode file {file_path} with any common encoding")

    def create_batches(self, text: str) -> List[TextBatch]:
        """
        Split text into batches respecting sentence boundaries.

        Args:
            text: Text to batch

        Returns:
            List of TextBatch objects
        """
        if not text.strip():
            return []

        batches = []
        current_pos = 0
        batch_index = 0

        while current_pos < len(text):
            # Calculate end position
            end_pos = min(current_pos + self.max_chars, len(text))

            # If not at the end, try to find a good break point
            if end_pos < len(text):
                # Look for sentence ending in the last 20% of the batch
                search_start = int(end_pos - self.max_chars * 0.2)
                remaining_text = text[search_start : end_pos + 100]  # Look ahead a bit

                # Try to find sentence boundaries
                sentence_endings = list(re.finditer(r"[.!?]\s+", remaining_text))

                if sentence_endings:
                    # Use the last sentence ending found
                    last_ending = sentence_endings[-1]
                    end_pos = search_start + last_ending.end()
                else:
                    # Fall back to paragraph break
                    paragraph_break = remaining_text.rfind("\n\n")
                    if paragraph_break > 0:
                        end_pos = search_start + paragraph_break + 2
                    else:
                        # Last resort: word boundary
                        space_pos = text[:end_pos].rfind(" ")
                        if space_pos > current_pos:
                            end_pos = space_pos + 1

            # Create batch
            batch_text = text[current_pos:end_pos].strip()

            if batch_text:  # Only add non-empty batches
                batches.append(
                    TextBatch(
                        text=batch_text,
                        start_char=current_pos,
                        end_char=end_pos,
                        batch_index=batch_index,
                    )
                )
                batch_index += 1

            current_pos = end_pos

        return batches

    def process_file(self, file_path: str) -> List[TextBatch]:
        """
        Read and batch a text file in one operation.

        Args:
            file_path: Path to the text file

        Returns:
            List of TextBatch objects
        """
        text = self.read_file(file_path)
        return self.create_batches(text)

    def estimate_batches(self, file_path: str) -> int:
        """
        Estimate number of batches without full processing.

        Args:
            file_path: Path to the text file

        Returns:
            Estimated number of batches
        """
        text = self.read_file(file_path)
        return max(1, (len(text) + self.max_chars - 1) // self.max_chars)
