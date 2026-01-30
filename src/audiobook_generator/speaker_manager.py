"""Multi-speaker management for audiobooks."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class Speaker:
    """Represents a speaker/character in the audiobook."""

    id: str
    name: str
    design_instruct: str
    reference_audio_path: Optional[str] = None
    voice_clone_prompt: Optional[any] = None


@dataclass
class TextSegment:
    """Text segment with speaker assignment."""

    text: str
    speaker_id: str
    segment_index: int
    batch_index: int
    is_dialogue: bool = False


class SpeakerManager:
    """Manages multiple speakers and dialogue detection."""

    def __init__(self):
        """Initialize speaker manager."""
        self.speakers: Dict[str, Speaker] = {}
        self.default_speaker_id = "narrator"

        # Add default narrator
        self.add_speaker(
            speaker_id="narrator",
            name="Narrator",
            design_instruct=(
                "Male, 35 years old, warm and engaging narrator voice, "
                "clear articulation, professional audiobook narrator tone"
            ),
        )

    def add_speaker(
        self,
        speaker_id: str,
        name: str,
        design_instruct: str,
        reference_audio_path: Optional[str] = None,
    ) -> Speaker:
        """
        Add a speaker to the manager.

        Args:
            speaker_id: Unique identifier for the speaker
            name: Display name
            design_instruct: Voice design instructions
            reference_audio_path: Optional path to reference audio

        Returns:
            Created Speaker object
        """
        speaker = Speaker(
            id=speaker_id,
            name=name,
            design_instruct=design_instruct,
            reference_audio_path=reference_audio_path,
        )

        self.speakers[speaker_id] = speaker
        logger.info(f"Added speaker: {name} ({speaker_id})")

        return speaker

    def get_speaker(self, speaker_id: str) -> Optional[Speaker]:
        """Get speaker by ID."""
        return self.speakers.get(speaker_id)

    def detect_dialogue(self, text: str) -> List[Tuple[str, str, bool]]:
        """
        Detect dialogue in text and split into segments.

        Args:
            text: Text to analyze

        Returns:
            List of (text_segment, speaker_id, is_dialogue) tuples
        """
        segments = []

        # Simple dialogue detection: Look for quoted text
        # Pattern matches: "dialogue" or 'dialogue'
        dialogue_pattern = r'(["\'])([^"\']+)\1'

        last_end = 0

        for match in re.finditer(dialogue_pattern, text):
            start, end = match.span()

            # Add narration before dialogue
            if start > last_end:
                narration = text[last_end:start].strip()
                if narration:
                    segments.append((narration, self.default_speaker_id, False))

            # Add dialogue (use default for now, can be enhanced with speaker detection)
            dialogue = match.group(2).strip()
            if dialogue:
                segments.append((dialogue, self.default_speaker_id, True))

            last_end = end

        # Add remaining narration
        if last_end < len(text):
            narration = text[last_end:].strip()
            if narration:
                segments.append((narration, self.default_speaker_id, False))

        # If no dialogue found, treat entire text as narration
        if not segments:
            segments.append((text.strip(), self.default_speaker_id, False))

        return segments

    def assign_speakers_to_batches(
        self, batches: List[str], enable_dialogue_detection: bool = False
    ) -> List[TextSegment]:
        """
        Assign speakers to text batches.

        Args:
            batches: List of text batches
            enable_dialogue_detection: Whether to detect and split dialogue

        Returns:
            List of TextSegment objects with speaker assignments
        """
        segments = []
        segment_index = 0

        for batch_index, batch_text in enumerate(batches):
            if enable_dialogue_detection:
                # Split batch into dialogue/narration segments
                detected_segments = self.detect_dialogue(batch_text)

                for text, speaker_id, is_dialogue in detected_segments:
                    segments.append(
                        TextSegment(
                            text=text,
                            speaker_id=speaker_id,
                            segment_index=segment_index,
                            batch_index=batch_index,
                            is_dialogue=is_dialogue,
                        )
                    )
                    segment_index += 1
            else:
                # Use entire batch with default speaker
                segments.append(
                    TextSegment(
                        text=batch_text,
                        speaker_id=self.default_speaker_id,
                        segment_index=segment_index,
                        batch_index=batch_index,
                        is_dialogue=False,
                    )
                )
                segment_index += 1

        logger.info(
            f"Created {len(segments)} segments from {len(batches)} batches "
            f"(dialogue detection: {enable_dialogue_detection})"
        )

        return segments

    def group_segments_by_speaker(
        self, segments: List[TextSegment]
    ) -> Dict[str, List[TextSegment]]:
        """
        Group segments by speaker for batch processing.

        Args:
            segments: List of text segments

        Returns:
            Dictionary mapping speaker_id to list of segments
        """
        grouped = {}

        for segment in segments:
            if segment.speaker_id not in grouped:
                grouped[segment.speaker_id] = []
            grouped[segment.speaker_id].append(segment)

        logger.info(f"Grouped {len(segments)} segments into {len(grouped)} speakers")

        return grouped
