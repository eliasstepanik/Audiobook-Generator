"""Speaker detection and analysis using LLM."""

from typing import List, Dict, Optional
import logging
import json
import re

from .llm_client import LLMClient

logger = logging.getLogger(__name__)


class SpeakerDetector:
    """Detects and identifies speakers/characters in text using LLM."""

    def __init__(self, llm_client: LLMClient):
        """
        Initialize speaker detector.

        Args:
            llm_client: LLM client for text analysis
        """
        self.llm_client = llm_client
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
        result = self.llm_client.process_text(
            text=analysis_text,
            batch_index=0,
            custom_prompt=self.speaker_detection_prompt,
            temperature=0.1,  # Low temperature for more consistent JSON output
            max_tokens=2000,  # Enough for JSON response with multiple speakers
        )

        # Parse JSON response
        try:
            response_text = result.processed_text.strip()

            # Remove markdown code blocks if present
            if "```" in response_text:
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines if not line.strip().startswith("```")
                ).strip()

            # Extract JSON from response - model may include preamble text
            json_start = response_text.find("{")
            if json_start > 0:
                logger.info(f"Stripping {json_start} chars of preamble before JSON")
                response_text = response_text[json_start:]

            # Try to fix incomplete JSON by finding the last complete object
            if not response_text.rstrip().endswith("}"):
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

    def split_text_into_segments(
        self, text: str, detected_speakers: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Split text into ordered segments with speaker assignments using LLM.

        Each segment represents a contiguous part of the text spoken by one speaker.
        Narration is assigned to "narrator", dialogue to the character speaking it.

        Args:
            text: Full text to split
            detected_speakers: List of detected speaker definitions

        Returns:
            List of dicts with 'text', 'speaker_id', 'speaker_name', 'segment_index'
            in reading order
        """
        logger.info("Splitting text into speaker segments...")

        # Build speaker list for prompt
        speaker_list = "\n".join(
            f"- {s['id']}: {s['name']} - {s['description']}" for s in detected_speakers
        )

        split_prompt = f"""You are splitting narrative text into ordered segments for multi-voice audiobook generation.

Available speakers:
{speaker_list}

TASK: Break the text into sequential segments. Each segment is a contiguous piece of text spoken by ONE speaker. Narration goes to "narrator", dialogue goes to the character who speaks it.

For EACH segment, also provide a "delivery" instruction describing HOW this specific segment should be spoken. The delivery should reflect the emotional context, pacing, and intensity of that exact moment in the story.

Return ONLY a valid JSON object in this exact format:
{{
  "segments": [
    {{"speaker_id": "narrator", "text": "...", "delivery": "calm, steady, setting the scene"}},
    {{"speaker_id": "character_id", "text": "...", "delivery": "slow, deliberate, with quiet intensity"}},
    {{"speaker_id": "narrator", "text": "...", "delivery": "faster, breathless, building tension"}}
  ]
}}

DELIVERY EXAMPLES (adapt to the actual text context):
- Tension building: "slower pace, hushed, quiet intensity, weighted pauses"
- Excitement: "faster pace, energetic, breathless, rising pitch"
- Fear/dread: "trembling, whispered, halting, nervous pauses"
- Wonder/realization: "soft, awestruck, gradually building, breathless"
- Calm/contemplative: "soft, dreamy, measured pace, gentle"
- Anger: "sharp, forceful, clipped words, intense"
- Sadness: "subdued, slow, wavering, heavy"
- Climactic moment: "dramatic, weighted pauses, powerful, resonant"
- Whispering: "hushed, barely audible, intimate"
- Shouting: "loud, commanding, forceful, projected"
- Sarcasm: "dry, flat delivery, slight edge"
- Mysterious: "low, slow, enigmatic, deliberate"

RULES:
1. Keep segments in exact reading order
2. Include ALL text - do not skip or summarize anything
3. Use exact text from the input - do not paraphrase or modify
4. Narration/description/attribution (e.g. "said the wizard") goes to "narrator"
5. Only the actual spoken words of a character go to that character's speaker_id
6. If unsure who speaks, assign to "narrator"
7. Return ONLY valid JSON, no markdown, no explanations
8. Keep the original text exactly as written
9. ALWAYS include a "delivery" field for every segment - tailor it to the emotional moment"""

        try:
            result = self.llm_client.process_text(
                text=text,
                batch_index=0,
                custom_prompt=split_prompt,
                temperature=0.1,
                max_tokens=8000,
            )

            # Parse response
            response_text = result.processed_text.strip()

            # Remove markdown code blocks
            if "```" in response_text:
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines if not line.strip().startswith("```")
                ).strip()

            # Extract JSON - model may include preamble text
            json_start = response_text.find("{")
            if json_start > 0:
                logger.info(f"Stripping {json_start} chars of preamble before JSON")
                response_text = response_text[json_start:]

            # Fix incomplete JSON
            if not response_text.rstrip().endswith("}"):
                last_complete = response_text.rfind("}]")
                if last_complete > 0:
                    response_text = response_text[: last_complete + 2] + "}"

            data = json.loads(response_text)
            segments = data.get("segments", [])

            if not segments:
                raise ValueError("No segments returned by LLM")

            # Build speaker name lookup
            speaker_names = {s["id"]: s["name"] for s in detected_speakers}

            # Validate and enrich segments
            result_segments = []
            for idx, seg in enumerate(segments):
                speaker_id = seg.get("speaker_id", "narrator")
                text_content = seg.get("text", "").strip()
                delivery = seg.get("delivery", "").strip()

                if not text_content:
                    continue

                # Validate speaker_id exists
                if speaker_id not in speaker_names:
                    logger.warning(
                        f"Unknown speaker_id '{speaker_id}', falling back to narrator"
                    )
                    speaker_id = "narrator"

                result_segments.append(
                    {
                        "text": text_content,
                        "speaker_id": speaker_id,
                        "speaker_name": speaker_names.get(speaker_id, "Narrator"),
                        "delivery": delivery,  # Per-segment delivery style
                        "segment_index": idx,
                    }
                )

            logger.info(
                f"Split text into {len(result_segments)} segments across {len(set(s['speaker_id'] for s in result_segments))} speakers"
            )
            return result_segments

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to split text with LLM: {e}")
            logger.info("Falling back to regex-based splitting")
            return self._fallback_split(text, detected_speakers)

    def _fallback_split(
        self, text: str, detected_speakers: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Fallback: split text into segments using regex-based dialogue detection.

        Splits on quoted dialogue vs narration. Assigns all dialogue to "narrator"
        if speaker cannot be determined.

        Args:
            text: Full text to split
            detected_speakers: List of detected speaker definitions

        Returns:
            List of segment dicts in reading order
        """
        logger.info("Using fallback regex-based text splitting")

        # Build name-to-id mapping from detected speakers
        name_to_id = {}
        for s in detected_speakers:
            name_to_id[s["name"].lower()] = s["id"]
            # Also map common variations
            name_parts = s["name"].lower().split()
            for part in name_parts:
                if part not in ("the", "a", "an", "old", "young", "mr", "mrs", "dr"):
                    name_to_id[part] = s["id"]

        speaker_names = {s["id"]: s["name"] for s in detected_speakers}

        # Pattern: Match narration and dialogue alternating
        # Splits on quoted speech: "..." or '...' with optional attribution
        # This regex captures: (narration before quote)(quoted text)(attribution after quote)
        pattern = r'([^"\u201c\u201d]*?)(\u201c[^\u201d]+\u201d|"[^"]+")([^"\u201c\u201d]*?)(?=\s*(?:\u201c|"|$))'

        segments = []
        last_end = 0
        segment_idx = 0

        # Try to find dialogue patterns
        for match in re.finditer(pattern, text):
            narration_before = match.group(1).strip()
            dialogue = match.group(2).strip()
            attribution = match.group(3).strip()

            # Add narration before dialogue
            if narration_before:
                segments.append(
                    {
                        "text": narration_before,
                        "speaker_id": "narrator",
                        "speaker_name": "Narrator",
                        "delivery": "",
                        "segment_index": segment_idx,
                    }
                )
                segment_idx += 1

            # Try to detect speaker from attribution or nearby text
            speaker_id = "narrator"
            context = (narration_before + " " + attribution).lower()
            for name, sid in name_to_id.items():
                if name in context:
                    speaker_id = sid
                    break

            # Add dialogue
            segments.append(
                {
                    "text": dialogue,
                    "speaker_id": speaker_id,
                    "speaker_name": speaker_names.get(speaker_id, "Narrator"),
                    "delivery": "",
                    "segment_index": segment_idx,
                }
            )
            segment_idx += 1

            # Add attribution as narration
            if attribution:
                segments.append(
                    {
                        "text": attribution,
                        "speaker_id": "narrator",
                        "speaker_name": "Narrator",
                        "delivery": "",
                        "segment_index": segment_idx,
                    }
                )
                segment_idx += 1

            last_end = match.end()

        # Add any remaining text
        remaining = text[last_end:].strip()
        if remaining:
            segments.append(
                {
                    "text": remaining,
                    "speaker_id": "narrator",
                    "speaker_name": "Narrator",
                    "delivery": "",
                    "segment_index": segment_idx,
                }
            )

        # If no segments were found, just return everything as narrator
        if not segments:
            segments.append(
                {
                    "text": text.strip(),
                    "speaker_id": "narrator",
                    "speaker_name": "Narrator",
                    "delivery": "",
                    "segment_index": 0,
                }
            )

        logger.info(f"Fallback split: {len(segments)} segments")
        return segments
