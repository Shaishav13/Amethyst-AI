"""
Comprehensive Test Suite for Amethyst AI ImageTaskRouter
=========================================================
Validates the complete specification matrix, multi-stage plans,
anatomical constraints, and edge cases offline without GPU overhead.
"""

import sys
import unittest

sys.path.append(r"D:\project2.0\AI_Assistant")
from image_task_router import ImageTaskRouter, TaskIntent, EditType


class TestImageTaskRouter(unittest.TestCase):
    def setUp(self):
        self.router = ImageTaskRouter()

    # Case 1: Attire Edit (Red Satin Evening Gown)
    def test_case_1_attire_gown(self):
        prompt = "Can you change her outfit into a red satin evening gown?"
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertFalse(plan.is_multi_stage)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.edit_type, EditType.ATTIRE)
        self.assertIn("red satin evening gown", stage.prompt_payload.lower())
        self.assertTrue(stage.supported)
        self.assertEqual(stage.preferred_engine, "sdxl")

    # Case 2: Bottom-only Attire Replacement (Jeans -> Trousers)
    def test_case_2_bottom_only(self):
        prompt = "Replace his jeans with black formal trousers."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.edit_type, EditType.ATTIRE)
        self.assertTrue(stage.categories.get("Pants"))
        self.assertFalse(stage.categories.get("Upper-clothes"))
        self.assertFalse(stage.categories.get("Dress"))

    # Case 3: Top-only Attire Replacement (Top -> Silk Blouse)
    def test_case_3_top_only(self):
        prompt = "Change her top to emerald-green silk."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.edit_type, EditType.ATTIRE)
        self.assertIn("emerald-green silk", stage.prompt_payload.lower())
        self.assertTrue(stage.categories.get("Upper-clothes"))
        self.assertFalse(stage.categories.get("Pants"))
        self.assertFalse(stage.categories.get("Skirt"))

    # Case 4: Sleeveless Attire / Bare Limbs Protected
    def test_case_4_sleeveless_protection(self):
        prompt = "Put her in a sleeveless emerald blouse."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.edit_type, EditType.ATTIRE)
        self.assertFalse(stage.categories.get("Left-arm"))
        self.assertFalse(stage.categories.get("Right-arm"))
        self.assertIn("bare_arms", stage.protected_attributes)
        self.assertNotIn(EditType.BACKGROUND, [s.edit_type for s in plan.stages])

    # Case 5: Background Only (Snowy Mountain)
    def test_case_5_background_only(self):
        prompt = "Move the subject to a snowy mountain."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.edit_type, EditType.BACKGROUND)
        self.assertIn("snowy mountain", stage.prompt_payload.lower())
        self.assertNotIn(EditType.ATTIRE, [s.edit_type for s in plan.stages])

    # Case 6: Background Only (Japanese Garden)
    def test_case_6_japanese_garden(self):
        prompt = "Put her in a Japanese garden."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.edit_type, EditType.BACKGROUND)
        self.assertIn("japanese garden", stage.prompt_payload.lower())
        self.assertNotIn(EditType.ATTIRE, [s.edit_type for s in plan.stages])

    # Case 7: Scenario Change (Cinematic Rainy-Night Scene)
    def test_case_7_scenario_change(self):
        prompt = "Turn this into a cinematic rainy-night scene."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.edit_type, EditType.BACKGROUND)
        self.assertIn("cinematic rainy-night scene", stage.prompt_payload.lower())

    # Case 8: Pose Edit (Unsupported Graceful Reporting)
    def test_case_8_pose_unsupported(self):
        prompt = "Make her stand with her arms crossed."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.edit_type, EditType.POSE)
        self.assertFalse(stage.supported, "Pose edit must be flagged unsupported based on audit")
        self.assertIsNotNone(stage.unavailable_reason)
        self.assertNotIn(EditType.ATTIRE, [s.edit_type for s in plan.stages])

    # Case 9: Combined Multi-Stage Edit (Attire + Background)
    def test_case_9_combined_attire_background(self):
        prompt = "Change her dress to black and replace the background with a castle."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertTrue(plan.is_multi_stage)
        self.assertEqual(len(plan.stages), 2)
        
        self.assertEqual(plan.stages[0].edit_type, EditType.ATTIRE)
        self.assertIn("black", plan.stages[0].prompt_payload.lower())
        self.assertEqual(plan.stages[1].edit_type, EditType.BACKGROUND)
        self.assertIn("castle", plan.stages[1].prompt_payload.lower())

    # Case 10: Combined Multi-Stage Edit (Jacket + Tokyo Night)
    def test_case_10_combined_jacket_tokyo(self):
        prompt = "Give her a black leather jacket and put her in Tokyo at night."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertTrue(plan.is_multi_stage)
        self.assertEqual(len(plan.stages), 2)
        
        self.assertEqual(plan.stages[0].edit_type, EditType.ATTIRE)
        self.assertIn("black leather jacket", plan.stages[0].prompt_payload.lower())
        self.assertEqual(plan.stages[1].edit_type, EditType.BACKGROUND)
        self.assertIn("tokyo at night", plan.stages[1].prompt_payload.lower())

    # Case 11: 3-Stage Edit (Attire + Pose + Background)
    def test_case_11_three_stage_edit(self):
        prompt = "Change her outfit to a black leather jacket, make her stand with her arms crossed, and place her on a rainy Tokyo street at night."
        plan = self.router.plan_task(prompt, has_reference_image=True)

        self.assertEqual(plan.intent, TaskIntent.IMAGE_EDIT)
        self.assertTrue(plan.is_multi_stage)
        self.assertEqual(len(plan.stages), 3)

        self.assertEqual(plan.stages[0].edit_type, EditType.ATTIRE)
        self.assertIn("black leather jacket", plan.stages[0].prompt_payload.lower())
        self.assertTrue(plan.stages[0].supported)

        self.assertEqual(plan.stages[1].edit_type, EditType.POSE)
        self.assertIn("stand with her arms crossed", plan.stages[1].prompt_payload.lower())
        self.assertFalse(plan.stages[1].supported)

        self.assertEqual(plan.stages[2].edit_type, EditType.BACKGROUND)
        self.assertIn("rainy tokyo street at night", plan.stages[2].prompt_payload.lower())
        self.assertTrue(plan.stages[2].supported)

    # Case 12: Text-to-Image from Scratch
    def test_case_12_txt2img_scratch(self):
        prompt = "Create a fantasy queen with silver armor from scratch."
        plan = self.router.plan_task(prompt, has_reference_image=False)

        self.assertEqual(plan.intent, TaskIntent.TXT2IMG)
        self.assertFalse(plan.has_reference_image)
        self.assertIn("fantasy queen with silver armor", plan.stages[0].prompt_payload.lower())

    # Case 13: Full Generation (Cyberpunk Warrior)
    def test_case_13_full_generation(self):
        prompt = "Create a cyberpunk warrior in a neon-lit city."
        plan = self.router.plan_task(prompt, has_reference_image=False)

        self.assertEqual(plan.intent, TaskIntent.TXT2IMG)
        self.assertFalse(plan.has_reference_image)
        self.assertIn("cyberpunk warrior in a neon-lit city", plan.stages[0].prompt_payload.lower())

    # Case 14: General Conversation (Ollama Route)
    def test_case_14_conversation_checkpoint(self):
        prompt = "How do I install a new ComfyUI checkpoint?"
        plan = self.router.plan_task(prompt, has_reference_image=False)

        self.assertEqual(plan.intent, TaskIntent.CONVERSATION)
        self.assertEqual(len(plan.stages), 0)
        self.assertFalse(plan.is_executable())

    # Case 15: General Conversation (Best Model Question)
    def test_case_15_conversation_best_model(self):
        prompt = "Which image model is best for portraits?"
        plan = self.router.plan_task(prompt, has_reference_image=False)

        self.assertEqual(plan.intent, TaskIntent.CONVERSATION)
        self.assertEqual(len(plan.stages), 0)
        self.assertFalse(plan.is_executable())

    # Case 16: Disambiguation (No Image vs With Image)
    def test_case_16_disambiguation(self):
        prompt = "A woman wearing a red coat walks through a snowy forest."
        # Without image attached -> routes cleanly to Txt2Img
        plan_no_img = self.router.plan_task(prompt, has_reference_image=False)
        self.assertEqual(plan_no_img.intent, TaskIntent.TXT2IMG)

        # With image attached -> triggers disambiguation prompt to protect user intent
        plan_with_img = self.router.plan_task(prompt, has_reference_image=True)
        self.assertEqual(plan_with_img.intent, TaskIntent.DISAMBIGUATION)
        self.assertTrue(plan_with_img.requires_user_clarification)
        self.assertIsNotNone(plan_with_img.clarification_message)


if __name__ == "__main__":
    unittest.main()
