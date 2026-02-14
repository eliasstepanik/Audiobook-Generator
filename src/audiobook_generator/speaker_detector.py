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
      "voice_characteristics": "Male, 35 years old, normal pitch, normal pace, clear articulation, warm and engaging voice"
    },
    {
      "id": "character_name",
      "name": "Character Name",
      "description": "Brief character description",
      "voice_characteristics": "Female, 25 years old, high-pitched, fast pace, clear articulation"
    }
  ]
}

CRITICAL - Include these DETAILED PARAMETERS for each speaker:
- Gender: male, female, or neutral
- Age: specific age (e.g., "25 years old", "elderly", "child")
- Pitch: very low-pitched, low-pitched, normal pitch, high-pitched, very high-pitched
- Pace: very slow, slow, normal, fast, very fast
- Clarity: clear, slightly unclear (if mumbled/slurred speech)
- Style: formal, casual (if relevant to character)

DO NOT include mood, tone, or emotional state in voice_characteristics. These are transient and should NOT define the voice identity. Focus ONLY on stable physical voice traits (gender, age, pitch, pace).

EXAMPLES OF GOOD voice_characteristics:
- "Young female voice, high-pitched, fast pace"
- "Low-pitched male voice, slow pace, elderly"
- "Female, 30 years old, normal pitch, fast pace, clear articulation"
- "Male, 45 years old, very low-pitched, very slow pace"
- "Child, 10 years old, high-pitched, fast pace"

IMPORTANT RULES:
- ONLY include a "narrator" speaker if there is actual narration text (descriptive prose, scene-setting, action descriptions)
- If the text is PURELY dialogue from one or more characters with NO narration, do NOT add a narrator
- If ALL text is spoken by a single character (monologue, speech, quest description), return ONLY that one speaker
- Be SPECIFIC - use exact parameters like "high-pitched, fast pace" not just "energetic voice"
- Match voice to character personality using PHYSICAL traits (villain = low pitch + slow pace, child = high pitch + fast pace)
- Match voice to age (child = high pitch + fast pace, elderly = low pitch + slow pace)
- Keep IDs as simple lowercase with underscores (e.g., "john_smith")
- Return ONLY valid JSON, no markdown formatting, no extra text

EXAMPLES:
- Text: "Hello, I need your help finding my lost cat." → 1 speaker (the person speaking)
- Text: "The sun set over the hills. 'We should go,' said Maria." → 2 speakers (narrator + Maria)
- Text: Pure monologue/speech → 1 speaker only (no narrator needed)"""

    def _get_incremental_detection_prompt(
        self, existing_speakers: List[Dict[str, str]]
    ) -> str:
        """Get prompt for detecting NEW speakers, given already-known speakers."""
        existing_list = "\n".join(
            f"- {s['id']}: {s['name']} ({s.get('description', 'no description')})"
            for s in existing_speakers
        )

        return f"""You are an expert at analyzing narrative text and identifying speakers/characters for audiobook narration.

ALREADY DETECTED SPEAKERS (do NOT include these again):
{existing_list}

Your task is to:
1. Identify any NEW distinct speakers/characters who have dialogue in THIS text section
2. ONLY return characters that are NOT already in the list above
3. For each NEW speaker, provide DETAILED voice characteristics

If you find NO new speakers, return: {{"speakers": []}}

Return ONLY a valid JSON object in this exact format:
{{
  "speakers": [
    {{
      "id": "new_character_name",
      "name": "New Character Name",
      "description": "Brief character description",
      "voice_characteristics": "Female, 25 years old, high-pitched, fast pace, clear articulation"
    }}
  ]
}}

CRITICAL - Include these DETAILED PARAMETERS for each NEW speaker:
- Gender: male, female, or neutral
- Age: specific age (e.g., "25 years old", "elderly", "child")
- Pitch: very low-pitched, low-pitched, normal pitch, high-pitched, very high-pitched
- Pace: very slow, slow, normal, fast, very fast
- Clarity: clear, slightly unclear (if mumbled/slurred speech)

DO NOT include mood, tone, or emotional state in voice_characteristics.

IMPORTANT RULES:
- Do NOT include any speaker that matches names/IDs in the ALREADY DETECTED list
- Only return genuinely NEW characters with speaking parts
- Keep IDs as simple lowercase with underscores
- Return ONLY valid JSON, no markdown formatting, no extra text
- If no new speakers found, return {{"speakers": []}}"""

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
            max_tokens=4000,  # Increased for more speakers
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

    def detect_speakers_iterative(
        self,
        text_chunks: List[str],
        batch_size_chars: int = 50000,
        progress_callback: Optional[callable] = None,
    ) -> List[Dict[str, str]]:
        """
        Detect speakers iteratively across multiple text chunks.

        Processes the entire text in batches, accumulating new characters
        as they are discovered. This ensures all characters throughout
        a book are detected, not just those in the first section.

        Args:
            text_chunks: List of text chunks (e.g., chapters) to analyze
            batch_size_chars: Max characters per LLM call
            progress_callback: Optional callback(batch_num, total_batches, speakers_found)

        Returns:
            List of all detected speaker dictionaries
        """
        all_speakers: List[Dict[str, str]] = []
        seen_ids: set = set()

        # Combine all chunks into one text for batching
        full_text = "\n\n".join(text_chunks)
        total_chars = len(full_text)

        # Calculate number of batches
        num_batches = (total_chars + batch_size_chars - 1) // batch_size_chars
        logger.info(
            f"Iterative speaker detection: {total_chars} chars in {num_batches} batches"
        )

        for batch_idx in range(num_batches):
            start = batch_idx * batch_size_chars
            end = min(start + batch_size_chars, total_chars)
            batch_text = full_text[start:end]

            logger.info(
                f"Processing batch {batch_idx + 1}/{num_batches} (chars {start}-{end})"
            )

            if batch_idx == 0:
                # First batch: use standard detection
                speakers = self.detect_speakers(
                    batch_text, max_analysis_chars=batch_size_chars
                )
                for s in speakers:
                    if s["id"] not in seen_ids:
                        all_speakers.append(s)
                        seen_ids.add(s["id"])
            else:
                # Subsequent batches: look for NEW speakers only
                new_speakers = self._detect_new_speakers(batch_text, all_speakers)
                for s in new_speakers:
                    if s["id"] not in seen_ids:
                        all_speakers.append(s)
                        seen_ids.add(s["id"])
                        logger.info(
                            f"New speaker found in batch {batch_idx + 1}: {s['name']}"
                        )

            if progress_callback:
                progress_callback(batch_idx + 1, num_batches, len(all_speakers))

        logger.info(
            f"Iterative detection complete: {len(all_speakers)} total speakers found"
        )
        return all_speakers

    def _detect_new_speakers(
        self, text: str, existing_speakers: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Detect only NEW speakers in a text chunk, given existing speakers.

        Args:
            text: Text chunk to analyze
            existing_speakers: List of already-detected speakers

        Returns:
            List of newly detected speaker dictionaries (may be empty)
        """
        if not text.strip():
            return []

        prompt = self._get_incremental_detection_prompt(existing_speakers)

        try:
            result = self.llm_client.process_text(
                text=text,
                batch_index=0,
                custom_prompt=prompt,
                temperature=0.1,
                max_tokens=4000,
            )

            response_text = result.processed_text.strip()

            # Remove markdown code blocks if present
            if "```" in response_text:
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines if not line.strip().startswith("```")
                ).strip()

            # Extract JSON
            json_start = response_text.find("{")
            if json_start > 0:
                response_text = response_text[json_start:]

            # Fix incomplete JSON
            if not response_text.rstrip().endswith("}"):
                last_complete = response_text.rfind("}]")
                if last_complete > 0:
                    response_text = response_text[: last_complete + 2] + "}"

            speakers_data = json.loads(response_text)
            new_speakers = speakers_data.get("speakers", [])

            # Filter out any that match existing IDs (double-check)
            existing_ids = {s["id"].lower() for s in existing_speakers}
            existing_names = {s["name"].lower() for s in existing_speakers}

            filtered = []
            for s in new_speakers:
                s_id = s.get("id", "").lower()
                s_name = s.get("name", "").lower()
                if s_id not in existing_ids and s_name not in existing_names:
                    filtered.append(s)

            return filtered

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to detect new speakers in chunk: {e}")
            return []

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

EMOTIONAL DELIVERY THROUGH PUNCTUATION:
The TTS model cannot receive emotion instructions directly. Instead, you must convey emotion through subtle punctuation adjustments in the text itself. This is the ONLY way to control delivery.

Allowed punctuation techniques (use sparingly and naturally):
- Ellipses "..." for hesitation, trailing off, or dramatic pauses
- Em-dashes "—" for abrupt interruptions or sharp breaks in thought
- Commas for natural breathing pauses in tense or slow moments
- Exclamation marks for emphasis, excitement, or urgency
- Question marks for uncertainty or rising intonation
- Short sentences for tension and urgency
- Longer flowing sentences for calm, contemplative moments

IMPORTANT: Keep the original WORDS intact. You may only adjust punctuation to hint at emotion. Do NOT add words, remove words, or rephrase.

Return ONLY a valid JSON object in this exact format:
{{
  "segments": [
    {{"speaker_id": "narrator", "text": "The room was silent. Nothing moved."}},
    {{"speaker_id": "character_id", "text": "I... I don't know what happened."}},
    {{"speaker_id": "narrator", "text": "She turned away — unable to face him."}}
  ]
}}

RULES:
1. Keep segments in exact reading order
2. Include ALL text - do not skip or summarize anything
3. Keep the original words exactly as written - only subtle punctuation adjustments are allowed
4. Narration/description/attribution (e.g. "said the wizard") goes to "narrator"
5. Only the actual spoken words of a character go to that character's speaker_id
6. If unsure who speaks, assign to "narrator"
7. Return ONLY valid JSON, no markdown, no explanations
8. Do NOT include a "delivery" field - emotion is conveyed through punctuation only"""

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
