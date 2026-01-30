"""Enhanced voice control with detailed parameters for TTS synthesis."""

from dataclasses import dataclass, field
from typing import Optional, Literal
from enum import Enum


class VoiceGender(str, Enum):
    """Voice gender options."""

    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


class VoicePace(str, Enum):
    """Speaking pace options."""

    VERY_SLOW = "very slow"
    SLOW = "slow"
    NORMAL = "normal"
    FAST = "fast"
    VERY_FAST = "very fast"


class VoiceTone(str, Enum):
    """Voice tone/emotion options."""

    NEUTRAL = "neutral"
    UPBEAT = "upbeat"
    CHEERFUL = "cheerful"
    ENERGETIC = "energetic"
    CALM = "calm"
    SERIOUS = "serious"
    RESTRAINED = "restrained"
    EXCITED = "excited"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    MYSTERIOUS = "mysterious"
    DRAMATIC = "dramatic"


class VoiceMood(str, Enum):
    """Voice mood options."""

    HAPPY = "happy"
    SAD = "sad"
    TIRED = "tired"
    ENERGETIC = "energetic"
    RELAXED = "relaxed"
    TENSE = "tense"
    CONFIDENT = "confident"
    UNCERTAIN = "uncertain"
    PLAYFUL = "playful"
    SERIOUS = "serious"


class VoicePitch(str, Enum):
    """Voice pitch options."""

    VERY_LOW = "very low-pitched"
    LOW = "low-pitched"
    NORMAL = "normal pitch"
    HIGH = "high-pitched"
    VERY_HIGH = "very high-pitched"


@dataclass
class DetailedVoiceProfile:
    """
    Detailed voice profile with granular control over all characteristics.

    Examples:
        # Young upbeat female
        profile = DetailedVoiceProfile(
            gender=VoiceGender.FEMALE,
            age=25,
            pace=VoicePace.FAST,
            tone=VoiceTone.UPBEAT,
            pitch=VoicePitch.NORMAL,
            description="A cheerful young woman's voice"
        )

        # Tired old male narrator
        profile = DetailedVoiceProfile(
            gender=VoiceGender.MALE,
            age=60,
            pace=VoicePace.SLOW,
            tone=VoiceTone.RESTRAINED,
            mood=VoiceMood.TIRED,
            pitch=VoicePitch.LOW,
            description="An elderly, weary narrator"
        )
    """

    # Basic characteristics
    gender: VoiceGender = VoiceGender.MALE
    age: int = 30  # Years old

    # Speech characteristics
    pace: VoicePace = VoicePace.NORMAL
    pitch: VoicePitch = VoicePitch.NORMAL
    tone: VoiceTone = VoiceTone.NEUTRAL
    mood: Optional[VoiceMood] = None

    # Descriptive
    description: str = "A clear, professional voice"
    language: str = "English"

    # Additional modifiers (for natural language instruction)
    clarity: Literal["clear", "slightly unclear", "mumbled"] = "clear"
    energy_level: Literal["low", "medium", "high"] = "medium"
    formality: Literal["casual", "neutral", "formal"] = "neutral"

    # Custom instruction (overrides all if provided)
    custom_instruction: Optional[str] = None

    def to_instruction(self) -> str:
        """
        Convert detailed profile to natural language instruction for TTS model.

        Returns:
            Natural language instruction string
        """
        if self.custom_instruction:
            return self.custom_instruction

        parts = []

        # Gender and age
        if self.gender != VoiceGender.NEUTRAL:
            parts.append(f"{self.gender.value}")
        if self.age:
            if self.age < 18:
                parts.append("child")
            elif self.age < 30:
                parts.append("young")
            elif self.age < 50:
                parts.append("middle-aged")
            else:
                parts.append("elderly")

        # Pitch
        if self.pitch != VoicePitch.NORMAL:
            parts.append(self.pitch.value)

        # Pace
        if self.pace != VoicePace.NORMAL:
            parts.append(f"{self.pace.value} pace")

        # Tone
        if self.tone != VoiceTone.NEUTRAL:
            parts.append(f"{self.tone.value} tone")

        # Mood
        if self.mood:
            parts.append(f"{self.mood.value} mood")

        # Energy
        if self.energy_level != "medium":
            if self.energy_level == "high":
                parts.append("energetic")
            elif self.energy_level == "low":
                parts.append("subdued")

        # Clarity
        if self.clarity != "clear":
            parts.append(self.clarity)

        # Formality
        if self.formality != "neutral":
            parts.append(f"{self.formality} style")

        # Combine
        if parts:
            instruction = ", ".join(parts).capitalize()
        else:
            instruction = "Natural, clear voice"

        # Add description if different from generated
        if self.description and self.description != "A clear, professional voice":
            instruction += f". {self.description}"

        return instruction

    @classmethod
    def from_natural_language(cls, instruction: str) -> "DetailedVoiceProfile":
        """
        Parse natural language instruction into DetailedVoiceProfile.

        Args:
            instruction: Natural language like "Young female voice, fast pace, upbeat tone"

        Returns:
            DetailedVoiceProfile instance
        """
        instruction_lower = instruction.lower()

        # Detect gender
        gender = VoiceGender.NEUTRAL
        if "male" in instruction_lower and "female" not in instruction_lower:
            gender = VoiceGender.MALE
        elif "female" in instruction_lower:
            gender = VoiceGender.FEMALE

        # Detect age
        age = 30  # Default
        if "young" in instruction_lower or "youth" in instruction_lower:
            age = 25
        elif "child" in instruction_lower or "kid" in instruction_lower:
            age = 10
        elif "teen" in instruction_lower:
            age = 16
        elif "old" in instruction_lower or "elderly" in instruction_lower:
            age = 60
        elif "middle" in instruction_lower:
            age = 45

        # Detect pace
        pace = VoicePace.NORMAL
        if "very slow" in instruction_lower:
            pace = VoicePace.VERY_SLOW
        elif "slow" in instruction_lower:
            pace = VoicePace.SLOW
        elif "very fast" in instruction_lower or "rapid" in instruction_lower:
            pace = VoicePace.VERY_FAST
        elif "fast" in instruction_lower or "quick" in instruction_lower:
            pace = VoicePace.FAST

        # Detect pitch
        pitch = VoicePitch.NORMAL
        if "very low" in instruction_lower or "deep" in instruction_lower:
            pitch = VoicePitch.VERY_LOW
        elif "low-pitch" in instruction_lower or "low pitch" in instruction_lower:
            pitch = VoicePitch.LOW
        elif "very high" in instruction_lower or "shrill" in instruction_lower:
            pitch = VoicePitch.VERY_HIGH
        elif "high-pitch" in instruction_lower or "high pitch" in instruction_lower:
            pitch = VoicePitch.HIGH

        # Detect tone
        tone = VoiceTone.NEUTRAL
        tone_map = {
            "upbeat": VoiceTone.UPBEAT,
            "cheerful": VoiceTone.CHEERFUL,
            "energetic": VoiceTone.ENERGETIC,
            "calm": VoiceTone.CALM,
            "serious": VoiceTone.SERIOUS,
            "restrained": VoiceTone.RESTRAINED,
            "excited": VoiceTone.EXCITED,
            "sad": VoiceTone.SAD,
            "angry": VoiceTone.ANGRY,
            "fearful": VoiceTone.FEARFUL,
            "mysterious": VoiceTone.MYSTERIOUS,
            "dramatic": VoiceTone.DRAMATIC,
        }
        for keyword, tone_val in tone_map.items():
            if keyword in instruction_lower:
                tone = tone_val
                break

        # Detect mood
        mood = None
        mood_map = {
            "happy": VoiceMood.HAPPY,
            "sad": VoiceMood.SAD,
            "tired": VoiceMood.TIRED,
            "weary": VoiceMood.TIRED,
            "energetic": VoiceMood.ENERGETIC,
            "relaxed": VoiceMood.RELAXED,
            "tense": VoiceMood.TENSE,
            "confident": VoiceMood.CONFIDENT,
            "uncertain": VoiceMood.UNCERTAIN,
            "playful": VoiceMood.PLAYFUL,
        }
        for keyword, mood_val in mood_map.items():
            if keyword in instruction_lower:
                mood = mood_val
                break

        # Detect energy level
        energy_level = "medium"
        if "energetic" in instruction_lower or "lively" in instruction_lower:
            energy_level = "high"
        elif "subdued" in instruction_lower or "low energy" in instruction_lower:
            energy_level = "low"

        # Detect clarity
        clarity = "clear"
        if "unclear" in instruction_lower or "mumbled" in instruction_lower:
            clarity = "slightly unclear"
        elif "crystal clear" in instruction_lower or "very clear" in instruction_lower:
            clarity = "clear"

        return cls(
            gender=gender,
            age=age,
            pace=pace,
            pitch=pitch,
            tone=tone,
            mood=mood,
            energy_level=energy_level,
            clarity=clarity,
            description=instruction,
            custom_instruction=None,  # Use parsed attributes
        )


# Preset voice profiles
PRESET_VOICES = {
    "narrator_professional": DetailedVoiceProfile(
        gender=VoiceGender.MALE,
        age=40,
        pace=VoicePace.NORMAL,
        tone=VoiceTone.NEUTRAL,
        pitch=VoicePitch.NORMAL,
        clarity="clear",
        formality="formal",
        description="Professional audiobook narrator with clear, warm voice",
    ),
    "narrator_friendly": DetailedVoiceProfile(
        gender=VoiceGender.FEMALE,
        age=35,
        pace=VoicePace.NORMAL,
        tone=VoiceTone.CHEERFUL,
        pitch=VoicePitch.NORMAL,
        clarity="clear",
        formality="casual",
        description="Friendly, approachable narrator with warm tone",
    ),
    "character_young_energetic": DetailedVoiceProfile(
        gender=VoiceGender.FEMALE,
        age=22,
        pace=VoicePace.FAST,
        tone=VoiceTone.UPBEAT,
        mood=VoiceMood.ENERGETIC,
        pitch=VoicePitch.HIGH,
        energy_level="high",
        description="Young, energetic character voice",
    ),
    "character_old_wise": DetailedVoiceProfile(
        gender=VoiceGender.MALE,
        age=65,
        pace=VoicePace.SLOW,
        tone=VoiceTone.CALM,
        mood=VoiceMood.RELAXED,
        pitch=VoicePitch.LOW,
        formality="formal",
        description="Elderly, wise character with deep, calm voice",
    ),
    "character_villain": DetailedVoiceProfile(
        gender=VoiceGender.MALE,
        age=45,
        pace=VoicePace.SLOW,
        tone=VoiceTone.MYSTERIOUS,
        mood=VoiceMood.TENSE,
        pitch=VoicePitch.LOW,
        energy_level="medium",
        description="Menacing villain with low, mysterious voice",
    ),
    "child_playful": DetailedVoiceProfile(
        gender=VoiceGender.NEUTRAL,
        age=10,
        pace=VoicePace.FAST,
        tone=VoiceTone.CHEERFUL,
        mood=VoiceMood.PLAYFUL,
        pitch=VoicePitch.HIGH,
        energy_level="high",
        formality="casual",
        description="Playful child's voice",
    ),
}


def create_voice_instruction(
    gender: Optional[str] = None,
    age: Optional[int] = None,
    pace: Optional[str] = None,
    tone: Optional[str] = None,
    mood: Optional[str] = None,
    pitch: Optional[str] = None,
    custom: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Helper function to create voice instruction from parameters.

    Args:
        gender: "male", "female", or "neutral"
        age: Age in years
        pace: "very slow", "slow", "normal", "fast", "very fast"
        tone: "upbeat", "calm", "serious", etc.
        mood: "happy", "tired", "energetic", etc.
        pitch: "very low", "low", "normal", "high", "very high"
        custom: Custom instruction (overrides all)
        **kwargs: Additional parameters

    Returns:
        Natural language instruction string

    Examples:
        >>> create_voice_instruction(gender="female", age=25, pace="fast", tone="upbeat")
        "Female, young, fast pace, upbeat tone"

        >>> create_voice_instruction(gender="male", age=60, pace="slow", mood="tired", pitch="low")
        "Male, elderly, low-pitched, slow pace, tired mood"
    """
    if custom:
        return custom

    profile = DetailedVoiceProfile(
        gender=VoiceGender(gender) if gender else VoiceGender.NEUTRAL,
        age=age if age else 30,
        pace=VoicePace(pace) if pace else VoicePace.NORMAL,
        tone=VoiceTone(tone) if tone else VoiceTone.NEUTRAL,
        mood=VoiceMood(mood) if mood else None,
        pitch=VoicePitch(pitch) if pitch else VoicePitch.NORMAL,
        **kwargs,
    )

    return profile.to_instruction()


if __name__ == "__main__":
    # Test examples
    print("=== Testing Voice Profile Generation ===\n")

    # Example 1: Young female, fast, upbeat
    profile1 = DetailedVoiceProfile(
        gender=VoiceGender.FEMALE, age=25, pace=VoicePace.FAST, tone=VoiceTone.UPBEAT
    )
    print("Profile 1:", profile1.to_instruction())

    # Example 2: Old male, slow, tired
    profile2 = DetailedVoiceProfile(
        gender=VoiceGender.MALE,
        age=60,
        pace=VoicePace.SLOW,
        tone=VoiceTone.RESTRAINED,
        mood=VoiceMood.TIRED,
        pitch=VoicePitch.LOW,
    )
    print("Profile 2:", profile2.to_instruction())

    # Example 3: From natural language
    profile3 = DetailedVoiceProfile.from_natural_language(
        "Young female voice, slightly faster pace, upbeat tone"
    )
    print("Profile 3 (parsed):", profile3.to_instruction())

    # Example 4: Using helper function
    instruction = create_voice_instruction(
        gender="male",
        age=45,
        pace="slow",
        tone="mysterious",
        pitch="low-pitched",  # Use correct enum value
    )
    print("Helper function:", instruction)

    # Example 5: Preset voices
    print("\n=== Preset Voices ===")
    for name, preset in PRESET_VOICES.items():
        print(f"{name}: {preset.to_instruction()}")
