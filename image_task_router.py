"""
Amethyst AI — Image Task Router & Execution Planner
===================================================
Converts natural-language user requests into structured, deterministic
image generation and editing execution plans.

Features:
- Pure natural-language intent understanding (zero forced CLI trigger prefixes).
- Distinguishes general conversation/coding questions from image tasks.
- Supports single-stage and multi-stage combined edits (attire + background + pose).
- Disambiguates descriptive captions from edit commands based on image presence.
- Enforces anatomical protections (face, hair, bare limbs for sleeveless tops).
- Gracefully detects missing/unsupported workflows (e.g., pose editing) without
  silent or destructive fallbacks.
- Fully backward-compatible with legacy prefixes (swap-outfit:, /image, generate-image:).
"""

import re
from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class TaskIntent(str, Enum):
    CONVERSATION = "conversation"          # General chat, questions about AI/models, coding
    TXT2IMG = "txt2img"                    # Generate new image from text
    IMAGE_EDIT = "image_edit"              # Edit existing active image (one or more stages)
    DISAMBIGUATION = "disambiguation"      # Ambiguous intent requiring context or user confirmation


class EditType(str, Enum):
    ATTIRE = "attire"                      # Clothing, accessories, garments
    BACKGROUND = "background"              # Environment, backdrop, scenery, location
    POSE = "pose"                          # Body posture, gestures, standing/sitting
    STYLE = "style"                        # Color grading, photographic filter, mood


class EditStage(BaseModel):
    order: int
    edit_type: EditType
    prompt_payload: str
    target_items: List[str] = Field(default_factory=list)
    categories: Dict[str, bool] = Field(default_factory=dict)
    protected_attributes: List[str] = Field(default_factory=list)
    preferred_engine: str = "sdxl"
    supported: bool = True
    unavailable_reason: Optional[str] = None


class ImageTaskPlan(BaseModel):
    intent: TaskIntent
    raw_prompt: str
    has_reference_image: bool
    is_multi_stage: bool = False
    stages: List[EditStage] = Field(default_factory=list)
    reasoning: str
    requires_user_clarification: bool = False
    clarification_message: Optional[str] = None

    def is_executable(self) -> bool:
        """Returns True if the plan has at least one supported executable stage."""
        if self.intent in (TaskIntent.CONVERSATION, TaskIntent.DISAMBIGUATION):
            return False
        if self.intent == TaskIntent.TXT2IMG:
            return True
        if self.intent == TaskIntent.IMAGE_EDIT:
            return any(s.supported for s in self.stages)
        return False


# ── REGEX KERNELS & PATTERNS ──────────────────────────────────────────────────

CONVERSATIONAL_PATTERNS = [
    r'^\s*(?:how\s+(?:do|can)\s+i|how\s+to|where\s+do\s+i|can\s+you\s+explain|what\s+is|what\s+are|which\s+(?:image\s+)?model|tell\s+me\s+about|why\s+does|compare|explain|help\s+(?:me\s+)?with)\b',
    r'\b(?:checkpoint|lora|safetensors|workflow|install|download|github|repository|version|parameter|setting)\b.*\?$',
    r'^\s*(?:hello|hi|hey|good\s+morning|who\s+are\s+you|thank\s+you|thanks)\b',
]

TXT2IMG_EXPLICIT_PATTERNS = [
    r'\b(?:from\s+scratch|brand\s+new(?:\s+image)?|generate\s+from\s+text|txt2img)\b',
    r'^\s*(?:create|generate|make|draw|paint|render)\s+(?:a|an|some)\s+(?:new\s+)?(?:image|photo|picture|illustration|painting|rendering|artwork)\s+of\b',
    r'^\s*(?:create|generate)\s+(?:a|an)\s+[^\n]+(?:from\s+scratch)\b',
    r'^\s*(?:generate[-_]?image|create[-_]?image|/image)\s*[:=-]?\s*',
]

EDIT_ACTION_VERBS = [
    r'\b(?:change|swap|replace|put|dress|give|turn|move|place|switch|modify|alter|make\s+her|make\s+him|make\s+them|set\s+(?:her|him|them|in))\b',
    r'^\s*(?:swap[-_]?outfit|edit[-_]?image|/edit)\s*[:=-]?\s*'
]

ATTIRE_KEYWORDS = [
    'outfit', 'cloth', 'clothes', 'clothing', 'dress', 'shirt', 't-shirt', 'blouse',
    'top', 'jacket', 'coat', 'hoodie', 'sweater', 'blazer', 'pant', 'pants', 'jeans',
    'shorts', 'trousers', 'skirt', 'suit', 'tuxedo', 'gown', 'vest', 'cardigan',
    'leather jacket', 'evening gown', 'swimsuit', 'bikini', 'uniform', 'costume',
    'armor', 'sari', 'kimono', 'robe'
]

BACKGROUND_KEYWORDS = [
    'background', 'backdrop', 'environment', 'scenery', 'scene', 'setting', 'location',
    'garden', 'mountain', 'mountains', 'beach', 'forest', 'street', 'city', 'tokyo',
    'paris', 'room', 'studio', 'castle', 'palace', 'indoor', 'outdoor', 'park',
    'terrace', 'balcony', 'night scene', 'rainy', 'snowy', 'desert', 'cafe'
]

POSE_KEYWORDS = [
    'arms crossed', 'crossing arms', 'sit', 'sitting', 'stand', 'standing',
    'lying down', 'walking', 'running', 'looking away', 'look over shoulder',
    'hands in pockets', 'pose', 'posture', 'gesture', 'kneeling', 'jumping'
]

CLAUSE_SPLIT_PATTERN = r'\s*(?:,\s*and\s+|\s+and\s+|,\s*)(?=(?:make\s+(?:her|him|them)|place\s+(?:her|him|them)|put\s+(?:her|him|them)|move\s+(?:her|him|the\s+subject)|replace\s+the\s+background|change\s+(?:the\s+)?(?:background|outfit|top|dress|clothes)|give\s+(?:her|him|them))\b)'


class ImageTaskRouter:
    """
    Intelligent natural language router for image generation and editing tasks.
    Evaluates capabilities dynamically and builds structured task plans.
    """

    def __init__(self, capabilities: Optional[Dict[str, bool]] = None):
        self.capabilities = capabilities or {
            "attire": True,
            "background": True,
            "txt2img": True,
            "pose": False,       # Audited: No pose-editing workflow installed
        }

    def plan_task(self, prompt: str, has_reference_image: bool = False, force_model: Optional[str] = None) -> ImageTaskPlan:
        """
        Main entry point: Analyzes prompt and context to construct a structured ImageTaskPlan.
        """
        text = (prompt or "").strip()
        lower = text.lower()

        # 1. Conversational / Informational Inquiry Intent
        if self._is_conversational(text, lower, has_reference_image, force_model):
            return ImageTaskPlan(
                intent=TaskIntent.CONVERSATION,
                raw_prompt=text,
                has_reference_image=has_reference_image,
                reasoning="Prompt is an informational inquiry or conversational query. Routing to Ollama text model."
            )

        # 2. Explicit Text-to-Image Generation
        if self._is_explicit_txt2img(text, lower, has_reference_image, force_model):
            clean_payload = self._extract_txt2img_payload(text)
            stage = EditStage(
                order=1,
                edit_type=EditType.STYLE,
                prompt_payload=clean_payload,
                preferred_engine="sdxl",
                supported=self.capabilities.get("txt2img", True)
            )
            return ImageTaskPlan(
                intent=TaskIntent.TXT2IMG,
                raw_prompt=text,
                has_reference_image=False,
                stages=[stage],
                reasoning="Explicit request to generate an image from scratch. Reference image not required."
            )

        # 3. Reference Image is Present
        if has_reference_image:
            has_edit_verb = any(re.search(p, lower) for p in EDIT_ACTION_VERBS)
            is_caption = self._is_descriptive_caption(lower)

            # Disambiguate descriptive captions when an image is attached
            if is_caption and not has_edit_verb:
                return ImageTaskPlan(
                    intent=TaskIntent.DISAMBIGUATION,
                    raw_prompt=text,
                    has_reference_image=True,
                    requires_user_clarification=True,
                    clarification_message=(
                        f"I noticed you provided a reference image with a descriptive prompt: \"{text}\". "
                        "Would you like me to edit the existing image with these details, "
                        "or generate a brand new image from scratch?"
                    ),
                    reasoning="Prompt is a descriptive caption with an attached image but lacks an explicit edit command verb."
                )

            # Detect specific edit intents
            has_attire = self._detect_attire_intent(lower)
            has_background = self._detect_background_intent(lower)
            has_pose = self._detect_pose_intent(lower)

            if has_edit_verb or has_attire or has_background or has_pose or force_model == "image":
                return self._build_edit_plan(text, lower, has_attire, has_background, has_pose)

        # 4. No Reference Image Attached
        has_edit_verb = any(re.search(p, lower) for p in EDIT_ACTION_VERBS)
        has_subject_pronoun = any(p in lower for p in ['her', 'his', 'their', 'the subject', 'this photo', 'the person'])
        if has_edit_verb and has_subject_pronoun:
            return ImageTaskPlan(
                intent=TaskIntent.IMAGE_EDIT,
                raw_prompt=text,
                has_reference_image=False,
                requires_user_clarification=True,
                clarification_message="You requested an image edit, but no reference photo was attached. Please attach or upload a photo to edit.",
                reasoning="Edit imperative detected on an existing subject, but no reference image is present in session."
            )

        # Default fallback without image: Text-to-Image
        clean_payload = self._extract_txt2img_payload(text)
        stage = EditStage(
            order=1,
            edit_type=EditType.STYLE,
            prompt_payload=clean_payload,
            preferred_engine="sdxl",
            supported=self.capabilities.get("txt2img", True)
        )
        return ImageTaskPlan(
            intent=TaskIntent.TXT2IMG,
            raw_prompt=text,
            has_reference_image=False,
            stages=[stage],
            reasoning="Descriptive prompt without reference image. Routing to Text-to-Image generation."
        )

    # ── INTENT CLASSIFIER HELPERS ─────────────────────────────────────────────

    def _is_conversational(self, text: str, lower: str, has_image: bool, force_model: Optional[str]) -> bool:
        if force_model == "image":
            return False
        for p in CONVERSATIONAL_PATTERNS:
            if re.search(p, lower):
                return True
        return False

    def _is_explicit_txt2img(self, text: str, lower: str, has_image: bool, force_model: Optional[str]) -> bool:
        if any(re.search(p, lower) for p in TXT2IMG_EXPLICIT_PATTERNS):
            return True
        return False

    def _detect_attire_intent(self, lower: str) -> bool:
        if any(k in lower for k in ATTIRE_KEYWORDS):
            return True
        if any(k in lower for k in ['outfit', 'wear', 'wearing', 'dressed in', 'clothed in', 'swap-outfit']):
            return True
        return False

    def _detect_background_intent(self, lower: str) -> bool:
        if any(k in lower for k in BACKGROUND_KEYWORDS):
            return True
        if any(k in lower for k in ['move the subject to', 'move her to', 'move him to', 'relocate to']):
            return True
        if re.search(r'\b(?:replace|change|swap)\s+(?:the\s+)?background\b', lower):
            return True
        if re.search(r'\bturn\s+this\s+into\s+[^\n,.]*scene\b', lower):
            return True
        return False

    def _detect_pose_intent(self, lower: str) -> bool:
        return any(k in lower for k in POSE_KEYWORDS)

    def _is_descriptive_caption(self, lower: str) -> bool:
        return bool(re.search(r'^\s*(?:a|an|the|portrait\s+of|photo\s+of|picture\s+of|close[- ]up\s+of|cinematic\s+shot\s+of)\b', lower))

    # ── EDIT PLAN BUILDER ─────────────────────────────────────────────────────

    def _build_edit_plan(self, text: str, lower: str, has_attire: bool, has_background: bool, has_pose: bool) -> ImageTaskPlan:
        # Strip legacy prefixes if present
        stripped_text = re.sub(r'(?i)^\s*(?:swap[-_]?outfit|edit[-_]?image|generate[-_]?image|create[-_]?image|/(?:image|edit))\s*[:=-]?\s*', '', text)
        
        # Split text into constituent clauses if multiple edit imperatives exist
        clauses = re.split(CLAUSE_SPLIT_PATTERN, stripped_text, flags=re.IGNORECASE)
        clauses = [c.strip() for c in clauses if c.strip()]

        attire_clause = stripped_text
        pose_clause = stripped_text
        bg_clause = stripped_text

        if len(clauses) > 1:
            for c in clauses:
                cl = c.lower()
                if self._detect_attire_intent(cl):
                    attire_clause = c
                if self._detect_pose_intent(cl):
                    pose_clause = c
                if self._detect_background_intent(cl):
                    bg_clause = c

        stages: List[EditStage] = []
        current_order = 1

        # Ordering: Attire -> Pose -> Background
        if has_attire or (not has_background and not has_pose):
            attire_payload, target_items, categories, protected = self._extract_attire_stage(attire_clause, attire_clause.lower())
            stages.append(EditStage(
                order=current_order,
                edit_type=EditType.ATTIRE,
                prompt_payload=attire_payload,
                target_items=target_items,
                categories=categories,
                protected_attributes=protected,
                preferred_engine="sdxl",
                supported=self.capabilities.get("attire", True),
                unavailable_reason=None if self.capabilities.get("attire", True) else "SDXL outfit inpainting workflow is unavailable."
            ))
            current_order += 1

        if has_pose:
            pose_payload, pose_items = self._extract_pose_stage(pose_clause, pose_clause.lower())
            is_supported = self.capabilities.get("pose", False)
            stages.append(EditStage(
                order=current_order,
                edit_type=EditType.POSE,
                prompt_payload=pose_payload,
                target_items=pose_items,
                protected_attributes=["face", "identity"],
                preferred_engine="controlnet",
                supported=is_supported,
                unavailable_reason=None if is_supported else "Pose-guided editing workflow is not installed. Amethyst will not perform an unsupported fallback."
            ))
            current_order += 1

        if has_background:
            bg_payload, bg_items = self._extract_background_stage(bg_clause, bg_clause.lower())
            stages.append(EditStage(
                order=current_order,
                edit_type=EditType.BACKGROUND,
                prompt_payload=bg_payload,
                target_items=bg_items,
                protected_attributes=["face", "hair", "subject_body", "glasses"],
                preferred_engine="flux",
                supported=self.capabilities.get("background", True),
                unavailable_reason=None if self.capabilities.get("background", True) else "Scenario replacement workflow is unavailable."
            ))
            current_order += 1

        is_multi = len(stages) > 1
        reasoning = f"Planned {len(stages)}-stage edit: " + " -> ".join(f"[{s.edit_type.value.upper()}] {s.prompt_payload}" for s in stages)

        return ImageTaskPlan(
            intent=TaskIntent.IMAGE_EDIT,
            raw_prompt=text,
            has_reference_image=True,
            is_multi_stage=is_multi,
            stages=stages,
            reasoning=reasoning
        )

    # ── PAYLOAD & STAGE EXTRACTORS ────────────────────────────────────────────

    def _extract_attire_stage(self, text: str, lower: str):
        # Strip legacy prefix
        text = re.sub(r'(?i)^\s*(?:swap[-_]?outfit|edit[-_]?image|generate[-_]?image|create[-_]?image|/(?:image|edit))\s*[:=-]?\s*', '', text)
        
        # Clean conversational imperatives with word boundaries
        cleaned = re.sub(
            r'(?i)^\s*(?:can\s+you\s+|please\s+|i\s+want\s+to\s+|could\s+you\s+)?\b(?:change|swap|replace|put|dress|give|turn)\b(?:\s+(?:her|his|their|the\s+person\'s|the\s+subject\'s))?(?:\s+\b(?:outfit|clothes|clothing|dress|attire|top|bottom)\b)?(?:\s+\b(?:into|in|with|to)\b)?\s*',
            '',
            text
        )
        cleaned = re.sub(r'(?i)\b(?:preserving\s+the\s+exact[^\n,.]*)\b', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,;.')

        target_items = [k for k in ATTIRE_KEYWORDS if k in lower]

        # Anatomical checks
        wants_arms = any(k in lower for k in ["long sleeve", "sleeves", "sleeve", "glove", "gloves", "cuff"])
        is_sleeveless = any(k in lower for k in ["sleeveless", "bare arms", "tank top", "strapless", "off-shoulder", "halter"])
        if is_sleeveless:
            wants_arms = False

        wants_legs = any(k in lower for k in ["stocking", "stockings", "tights", "leggings", "socks", "sock"])
        wants_shoes = any(k in lower for k in ["shoe", "shoes", "boot", "boots", "heels", "sneaker", "sneakers", "footwear"])

        # Detect bottom-only replacement
        is_bottom_only = any(k in lower for k in ["pants", "jeans", "skirt", "shorts", "trousers", "slacks"]) and not any(k in lower for k in ["shirt", "t-shirt", "jacket", "hoodie", "sweater", "blazer", "top", "coat", "blouse", "dress", "suit", "outfit", "attire", "gown"])
        
        # Detect top-only replacement
        is_top_only = any(k in lower for k in ["shirt", "t-shirt", "jacket", "hoodie", "sweater", "blazer", "top", "coat", "blouse"]) and not any(k in lower for k in ["dress", "skirt", "pants", "jeans", "shorts", "suit", "outfit", "attire", "gown", "trousers"])

        categories = {
            "Face": False,
            "Hair": False,
            "Hat": False,
            "Sunglasses": False,
            "Background": False,
            "Upper-clothes": True,
            "Skirt": True,
            "Dress": True,
            "Pants": True,
            "Belt": True,
            "Scarf": True,
            "Bag": True,
            "Left-arm": wants_arms,
            "Right-arm": wants_arms,
            "Left-leg": wants_legs,
            "Right-leg": wants_legs,
            "Left-shoe": wants_shoes,
            "Right-shoe": wants_shoes
        }

        if is_bottom_only:
            categories["Upper-clothes"] = False
            categories["Dress"] = False
        elif is_top_only:
            categories["Skirt"] = False
            categories["Pants"] = False
            categories["Left-leg"] = False
            categories["Right-leg"] = False
            categories["Left-shoe"] = False
            categories["Right-shoe"] = False

        protected = ["face", "hair", "glasses"]
        if not wants_arms:
            protected.extend(["exposed_shoulders", "bare_arms", "hands"])
        if not wants_legs:
            protected.append("exposed_legs")

        return cleaned or "tailored attire, realistic fabric", target_items, categories, protected

    def _extract_background_stage(self, text: str, lower: str):
        text = re.sub(r'(?i)^\s*(?:swap[-_]?outfit|edit[-_]?image|generate[-_]?image|create[-_]?image|/(?:image|edit))\s*[:=-]?\s*', '', text)
        bg_match = re.search(r'(?i)(?:and\s+)?(?:replace\s+the\s+background\s+with|change\s+(?:the\s+)?background\s+to|put\s+(?:her|him|them)\s+in\s+(?:a|an)?|move\s+(?:her|him|the\s+subject)\s+to\s+(?:a|an)?|place\s+(?:her|him|them)\s+(?:in|on)\s+(?:a|an)?|set\s+(?:her|him|in)\s+(?:a|an)?|turn\s+this\s+into\s+(?:a|an)?)\s*([^,;.]+)', text)
        if bg_match:
            bg_target = bg_match.group(1).strip()
        else:
            bg_target = re.sub(r'(?i)^\s*(?:put\s+her\s+in|move\s+the\s+subject\s+to|change\s+background\s+to|replace\s+background\s+with|place\s+her\s+on)\s*', '', text).strip(' ,;.')

        target_items = [k for k in BACKGROUND_KEYWORDS if k in lower]
        return bg_target or "cinematic environment, matching ambient lighting", target_items

    def _extract_pose_stage(self, text: str, lower: str):
        text = re.sub(r'(?i)^\s*(?:swap[-_]?outfit|edit[-_]?image|generate[-_]?image|create[-_]?image|/(?:image|edit))\s*[:=-]?\s*', '', text)
        pose_match = re.search(r'(?i)(?:make\s+(?:her|him|them)\s+)?(stand[^\n,.]*|sit[^\n,.]*|walk[^\n,.]*|arms\s+crossed[^\n,.]*|look[^\n,.]*|hands\s+in\s+pockets[^\n,.]*)', text)
        if pose_match:
            pose_target = pose_match.group(1).strip()
        else:
            pose_target = "natural confident posture"
        target_items = [k for k in POSE_KEYWORDS if k in lower]
        return pose_target, target_items

    def _extract_txt2img_payload(self, text: str):
        text = re.sub(r'(?i)^\s*(?:swap[-_]?outfit|edit[-_]?image|generate[-_]?image|create[-_]?image|/(?:image|edit))\s*[:=-]?\s*', '', text)
        cleaned = re.sub(r'(?i)^\s*(?:create|generate|make|draw|paint|render)\s+(?:a|an|some)\s+(?:new\s+)?(?:image|photo|picture|illustration|artwork)\s+of\s*', '', text)
        cleaned = re.sub(r'(?i)^\s*(?:create|generate|make)\s+(?:a|an)\s*', '', cleaned)
        cleaned = re.sub(r'(?i)\b(?:from\s+scratch)\b', '', cleaned)
        return re.sub(r'\s+', ' ', cleaned).strip(' ,;.')
