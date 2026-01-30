"""Speaker detection and analysis using LLM."""

from typing import List, Dict, Optional
import logging
import json

from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class SpeakerDetector:
    """Detects and identifies speakers/characters in text using LLM."""

    def __init__(self, ollama_client: OllamaClient):
        """
        Initialize speaker detector.

        Args:
            ollama_client: Ollama client for LLM analysis
        """
        self.ollama_client = ollama_client
        self.speaker_detection_prompt = self._get_detection_prompt()

    def _get_detection_prompt(self) -> str:
        """Get system prompt for speaker detection with detailed voice control."""
        return """You are an expert at analyzing narrative text and identifying speakers/characters for audiobook narration.

Your task is to:
1. Identify all distinct speakers/characters who have dialogue in the text
2. Determine the narrator voice needed
3. For each speaker, provide DETAILED voice characteristics with precise control parameters

Return ONLY a valid JSON object in this exact format:
{
  "speakers": [
    {
      "id": "narrator",
      "name": "Narrator",
      "description": "The main narrative voice",
      "voice_characteristics": "Male, 35 years old, normal pitch, normal pace, calm tone, clear articulation, warm and engaging voice"
    },
    {
      "id": "character_name",
      "name": "Character Name",
      "description": "Brief character description",
      "voice_characteristics": "Female, 25 years old, high-pitched, fast pace, upbeat tone, energetic mood, cheerful and lively voice"
    }
  ]
}

CRITICAL - Include these DETAILED PARAMETERS for each speaker:
- Gender: male, female, or neutral
- Age: specific age (e.g., "25 years old", "elderly", "child")
- Pitch: very low-pitched, low-pitched, normal pitch, high-pitched, very high-pitched
- Pace: very slow, slow, normal, fast, very fast
- Tone: upbeat, cheerful, calm, serious, restrained, energetic, mysterious, dramatic, sad, angry, fearful
- Mood (optional): happy, sad, tired, energetic, relaxed, tense, confident, uncertain, playful
- Energy level: low energy, medium energy, high energy
- Clarity: clear, slightly unclear (if mumbled/slurred speech)
- Style: formal, casual (if relevant to character)

EXAMPLES OF GOOD voice_characteristics:
- "Young female voice, high-pitched, fast pace, upbeat tone, energetic mood"
- "Low-pitched male voice, slow pace, restrained tone, tired mood, elderly"
- "Female, 30 years old, normal pitch, fast pace, cheerful tone, confident mood"
- "Male, 45 years old, very low-pitched, very slow pace, mysterious tone, tense mood"
- "Child, 10 years old, high-pitched, fast pace, playful tone, excited mood"

IMPORTANT RULES:
- Always include a "narrator" speaker
- Be SPECIFIC - use exact parameters like "high-pitched, fast pace" not just "energetic voice"
- Match voice to character personality (villain = low pitch + slow pace + mysterious)
- Match voice to age (child = high pitch + fast pace, elderly = low pitch + slow pace)
- Keep IDs as simple lowercase with underscores (e.g., "john_smith")
- Return ONLY valid JSON, no markdown formatting, no extra text"""

    def detect_speakers(
        self, processed_text: str, max_analysis_chars: int = 50000
    ) -> List[Dict[str, str]]:
        """
        Detect speakers in processed text.

        Args:
            processed_text: The full processed text to analyze
            max_analysis_chars: Maximum characters to analyze (for performance)

        Returns:
            List of speaker dictionaries with id, name, description, voice_characteristics
        """
        logger.info("Detecting speakers in text...")

        # Take a sample if text is too long
        analysis_text = processed_text[:max_analysis_chars]
        if len(processed_text) > max_analysis_chars:
            logger.info(
                f"Text truncated to {max_analysis_chars} chars for speaker detection"
            )

        # Ask LLM to identify speakers
        result = self.ollama_client.process_text(
            text=analysis_text,
            batch_index=0,
            custom_prompt=self.speaker_detection_prompt,
            temperature=0.1,  # Low temperature for more consistent JSON output
            max_tokens=2000,  # Enough for JSON response with multiple speakers
        )

        # Parse JSON response
        try:
            # Clean response - remove markdown code blocks if present
            response_text = result.processed_text.strip()
            if response_text.startswith("```"):
                # Remove markdown code blocks
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines if not line.strip().startswith("```")
                )

            # Try to fix incomplete JSON by finding the last complete object
            if not response_text.endswith("}"):
                # Find last complete closing bracket for the speakers array
                last_complete = response_text.rfind("}]")
                if last_complete > 0:
                    response_text = response_text[: last_complete + 2] + "}"

            speakers_data = json.loads(response_text)
            speakers = speakers_data.get("speakers", [])

            # Ensure narrator exists
            has_narrator = any(s.get("id") == "narrator" for s in speakers)
            if not has_narrator:
                logger.warning("No narrator found, adding default narrator")
                speakers.insert(
                    0,
                    {
                        "id": "narrator",
                        "name": "Narrator",
                        "description": "Main narrative voice",
                        "voice_characteristics": (
                            "Male, 35 years old, warm and engaging narrator voice, "
                            "clear articulation, professional audiobook narrator tone"
                        ),
                    },
                )

            logger.info(
                f"Detected {len(speakers)} speakers: {[s['name'] for s in speakers]}"
            )

            return speakers

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse speaker detection response: {e}")
            logger.error(f"Response was: {result.processed_text}")

            # Fallback to default narrator only
            logger.warning("Falling back to narrator-only mode")
            return [
                {
                    "id": "narrator",
                    "name": "Narrator",
                    "description": "Main narrative voice",
                    "voice_characteristics": (
                        "Male, 35 years old, warm and engaging narrator voice, "
                        "clear articulation, professional audiobook narrator tone"
                    ),
                }
            ]

    def assign_speakers_to_segments(
        self, text_segments: List[str], detected_speakers: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Assign detected speakers to text segments using LLM.

        Args:
            text_segments: List of text segments to assign speakers to
            detected_speakers: List of detected speaker definitions

        Returns:
            List of dicts with 'text' and 'speaker_id' keys
        """
        logger.info(f"Assigning speakers to {len(text_segments)} segments...")

        # Build speaker list for prompt
        speaker_list = "\n".join(
            f"- {s['id']}: {s['name']} ({s['voice_characteristics']})"
            for s in detected_speakers
        )

        assignment_prompt = f"""You are assigning speakers to text segments for audiobook narration.

Available speakers:
{speaker_list}

Rules:
1. Assign "narrator" to all narrative/descriptive text
2. Assign specific character IDs to their dialogue
3. When in doubt, use "narrator"

For each text segment, return ONLY a JSON array with speaker assignments:
[
  {{"speaker_id": "narrator"}},
  {{"speaker_id": "character_id"}},
  ...
]

Return ONLY valid JSON array, no markdown, no explanations."""

        # Process in batches to avoid context limits
        batch_size = 20
        all_assignments = []

        for i in range(0, len(text_segments), batch_size):
            batch = text_segments[i : i + batch_size]

            # Format segments for analysis
            segments_text = "\n\n---SEGMENT---\n".join(
                f"[{idx}] {seg[:500]}" for idx, seg in enumerate(batch)
            )

            try:
                result = self.ollama_client.process_text(
                    text=segments_text,
                    batch_index=i // batch_size,
                    custom_prompt=assignment_prompt,
                    temperature=0.1,
                )

                # Parse response
                response_text = result.processed_text.strip()
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    response_text = "\n".join(
                        line for line in lines if not line.strip().startswith("```")
                    )

                assignments = json.loads(response_text)
                all_assignments.extend(assignments)

            except Exception as e:
                logger.warning(f"Failed to assign speakers for batch {i}: {e}")
                # Fallback: assign narrator to all segments in this batch
                all_assignments.extend([{"speaker_id": "narrator"}] * len(batch))

        # Combine with text segments
        result = []
        for idx, segment in enumerate(text_segments):
            speaker_id = "narrator"  # default
            if idx < len(all_assignments):
                speaker_id = all_assignments[idx].get("speaker_id", "narrator")

            result.append(
                {"text": segment, "speaker_id": speaker_id, "segment_index": idx}
            )

        logger.info(f"Assigned speakers to all {len(result)} segments")

        return result
