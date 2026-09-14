import json
import unittest
from unittest.mock import Mock

from prithi_brain import BrainOutputError, PrithiBrain, RelationshipState


STYLE = {"energy": .5, "warmth": .6, "intimacy": .2, "playfulness": .2, "tenderness": .4, "pace": 1.0}


def response(reply, language="bengali", emotion="neutral"):
    return json.dumps({"reply": reply, "language": language, "emotion": emotion, "voice_style": STYLE}, ensure_ascii=False)


class SequenceBackend:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return self.outputs.pop(0)


class BehaviorStateTests(unittest.TestCase):
    def test_gradual_relationship_changes(self):
        brain = PrithiBrain(SequenceBackend(response("আজকে একটু বিশ্রাম নাও।", emotion="caring")))
        before = brain.relationship_state.as_dict()
        brain.respond("আজ খুব ক্লান্ত।", preferred_reply_language="bengali")
        after = brain.relationship_state.as_dict()
        self.assertTrue(all(abs(after[k] - before[k]) <= .03 for k in before))
        self.assertGreater(after["trust"], before["trust"])

    def test_values_clamped(self):
        state = RelationshipState(.99, .99, .99, .99, .99)
        state.apply(familiarity=.03, trust=.03, affection=.03, playfulness=.03, romantic_tension=.03)
        self.assertTrue(all(value == 1.0 for value in state.as_dict().values()))

    def test_emotion_continuity(self):
        brain = PrithiBrain(SequenceBackend(response("উফ, দিনটা কঠিন ছিল।", emotion="caring"), response("এখন একটু হালকা থাকো।", emotion="warm")))
        brain.respond("আজ খারাপ লাগছে।", preferred_reply_language="bengali")
        brain.respond("এখন একটু ভালো।", preferred_reply_language="bengali")
        self.assertEqual((brain.previous_emotion, brain.current_emotion), ("caring", "warm"))

    def test_no_neutral_to_aroused_jump(self):
        brain = PrithiBrain(SequenceBackend(response("না।", emotion="aroused"), response("এটা তো সাধারণ কথা।", emotion="neutral")))
        self.assertEqual(brain.respond("আজ আকাশ সুন্দর।", preferred_reply_language="bengali").emotion, "neutral")

    def test_ordinary_message_cannot_force_attraction(self):
        brain = PrithiBrain(SequenceBackend(response("ওহো।", emotion="attraction"), response("আকাশটা সত্যিই সুন্দর।", emotion="warm")))
        self.assertEqual(brain.respond("আজ আকাশ সুন্দর।", preferred_reply_language="bengali").emotion, "warm")

    def test_anti_repetition_retries(self):
        backend = SequenceBackend(response("আচ্ছা, তাই নাকি?", emotion="warm"), response("আচ্ছা, তাই নাকি?", emotion="warm"), response("ওহো, আজ বেশ মজার mood!", emotion="playful"))
        brain = PrithiBrain(backend)
        brain.respond("প্রথম কথা", preferred_reply_language="bengali")
        answer = brain.respond("দ্বিতীয় কথা", preferred_reply_language="bengali")
        self.assertEqual(answer.reply, "ওহো, আজ বেশ মজার mood!")

    def test_question_frequency_guidance(self):
        backend = SequenceBackend(response("আজ প্রশ্ন নয়।", emotion="neutral"))
        brain = PrithiBrain(backend)
        brain.recent_questions.extend([True, True, False])
        brain.respond("ঠিক আছে", preferred_reply_language="bengali")
        self.assertIn("Do not ask a question", str(backend.calls[0]))

    def test_question_frequency_is_guidance_not_a_failure(self):
        backend = SequenceBackend(response("এখন একটু ভালো লাগছে?", emotion="warm"))
        brain = PrithiBrain(backend)
        brain.recent_questions.extend([True, True])
        brain.respond("এখন একটু ভালো লাগছে", preferred_reply_language="bengali")
        self.assertIn("Do not ask a question", str(backend.calls[0]))

    def test_more_than_one_direct_question_retries(self):
        backend = SequenceBackend(
            response("কী হলো? এখন কেমন আছো?", emotion="caring"),
            response("আজ একটু ধীরে থাকো; আমি পাশে আছি।", emotion="caring"),
        )
        answer = PrithiBrain(backend).respond("আজ মন খারাপ", preferred_reply_language="bengali")
        self.assertEqual(answer.reply, "আজ একটু ধীরে থাকো; আমি পাশে আছি।")

    def test_allowed_adult_invitation_retries_unnecessary_refusal(self):
        backend = SequenceBackend(
            response("I can't help with that; let's keep it friendly.", "english", "neutral"),
            response("Come a little closer; I like the slow tension between us.", "english", "flirtatious"),
        )
        answer = PrithiBrain(backend).respond(
            "Let's flirt in a sensual mood", preferred_reply_language="english", conversation_mode="adult"
        )
        self.assertIn("slow tension", answer.reply)

    def test_sensitive_memory_reply_must_truthfully_reject_storage(self):
        backend = SequenceBackend(
            response("এটা খুব বিপজ্জনক।", emotion="caring"),
            response("এটা আমি সেভ করতে পারি না, তাই মনে রাখছি না।", emotion="caring"),
        )
        answer = PrithiBrain(backend).respond(
            "Remember my password is hunter2", preferred_reply_language="bengali"
        )
        self.assertIn("সেভ করতে পারি না", answer.reply)

    def test_premature_pet_name_retries(self):
        backend = SequenceBackend(response("বলো সোনা।", emotion="warm"), response("আচ্ছা, বলো।", emotion="warm"))
        brain = PrithiBrain(backend)
        self.assertEqual(brain.respond("হ্যালো", preferred_reply_language="bengali").reply, "আচ্ছা, বলো।")

    def test_counselor_boilerplate_retries(self):
        backend = SequenceBackend(response("বুঝতেই পারছি, খুব ক্লান্ত।", emotion="caring"), response("উফ, আজকের কাজ তোমাকে একদম নিংড়ে দিয়েছে।", emotion="caring"))
        brain = PrithiBrain(backend)
        self.assertIn("আজকের কাজ", brain.respond("আজ কাজের চাপ ছিল", preferred_reply_language="bengali").reply)

    def test_does_not_reask_what_happened_after_context_was_given(self):
        backend = SequenceBackend(
            response("উফ, আজকের কাজটা বেশ চাপের ছিল।", emotion="caring"),
            response("আরে, সত্যি? কী হয়েছে?", emotion="caring"),
            response("ভালো লাগছে যে কথাটা তোমাকে একটু হালকা করেছে।", emotion="warm"),
        )
        brain = PrithiBrain(backend)
        brain.respond("আজ অফিসে অনেক চাপ ছিল।", preferred_reply_language="bengali")
        answer = brain.respond("তোমার কথাটা শুনে একটু ভালো লাগছে।", preferred_reply_language="bengali")
        self.assertNotIn("কী হয়েছে", answer.reply)
        self.assertIn("হালকা", answer.reply)

    def test_prompt_prohibits_invented_offline_experience(self):
        backend = SequenceBackend(response("ম্যাচটা আমি দেখিনি, তবে তোমার excitement বেশ বোঝা যাচ্ছে।", emotion="neutral"))
        brain = PrithiBrain(backend)
        brain.respond("ম্যাচ দেখেছো?", preferred_reply_language="bengali")
        prompt = str(backend.calls[0])
        self.assertIn("Never claim physical or offline experiences", prompt)
        self.assertIn("Do not mention being AI", prompt)

    def test_cyrillic_leak_retries(self):
        backend = SequenceBackend(response("এই কথাটা cute, правда?", emotion="playful"), response("এই কথাটা কিন্তু বেশ cute!", emotion="playful"))
        brain = PrithiBrain(backend)
        self.assertNotIn("правда", brain.respond("সত্যি?", preferred_reply_language="bengali").reply)

    def test_false_match_claim_retries(self):
        backend = SequenceBackend(response("দেখেছি! দারুণ ম্যাচ ছিল।", emotion="neutral"), response("লাইভ দেখিনি, তবে ম্যাচটা নিয়ে তোমার excitement স্পষ্ট।", emotion="neutral"))
        brain = PrithiBrain(backend)
        self.assertTrue(brain.respond("কালকের ম্যাচ দেখেছো?", preferred_reply_language="bengali").reply.startswith("লাইভ দেখিনি"))

    def test_unverified_match_hearsay_retries(self):
        backend = SequenceBackend(response("শুনেছি, ম্যাচটা দারুণ ছিল!", emotion="neutral"), response("লাইভ দেখিনি—তোমার কাছে কেমন লেগেছে?", emotion="neutral"))
        brain = PrithiBrain(backend)
        self.assertTrue(brain.respond("কালকের ম্যাচ দেখেছো?", preferred_reply_language="bengali").reply.startswith("লাইভ দেখিনি"))

    def test_unverified_people_said_match_claim_retries(self):
        backend = SequenceBackend(response("অনেকে বলছিল ম্যাচটা দারুণ ছিল!", emotion="neutral"), response("আমি খেলাটা দেখিনি—তুমি দেখেছিলে?", emotion="neutral"))
        brain = PrithiBrain(backend)
        self.assertTrue(brain.respond("কালকের ম্যাচ দেখেছো?", preferred_reply_language="bengali").reply.startswith("আমি খেলাটা দেখিনি"))

    def test_history_callback_available(self):
        backend = SequenceBackend(response("অফিসের পর একটু বিশ্রাম নাও।", emotion="caring"), response("ভালো, কাজের পর এখন একটু শান্তি।", emotion="warm"))
        brain = PrithiBrain(backend)
        brain.respond("অফিসে অনেক কাজ ছিল।", preferred_reply_language="bengali")
        brain.respond("এখন শান্ত লাগছে।", preferred_reply_language="bengali")
        self.assertIn("অফিসে অনেক কাজ ছিল", str(backend.calls[1]))

    def test_reset_clears_relationship_and_emotion(self):
        brain = PrithiBrain(SequenceBackend(response("একটু বিশ্রাম নাও।", emotion="caring")))
        brain.respond("ক্লান্ত", preferred_reply_language="bengali")
        brain.reset_history()
        self.assertEqual(brain.relationship_state, RelationshipState())
        self.assertEqual(brain.debug_state()["current_emotion"], "neutral")
        self.assertEqual(brain.history_turn_count, 0)

    def test_session_isolation(self):
        a = PrithiBrain(SequenceBackend(response("তোমার জন্য মায়া লাগছে।", emotion="affectionate")))
        b = PrithiBrain(SequenceBackend(response("হ্যালো।", emotion="neutral")))
        a.respond("তোমাকে miss করেছি", preferred_reply_language="bengali")
        self.assertNotEqual(a.relationship_state, b.relationship_state)
        self.assertEqual(b.relationship_state, RelationshipState())


class BehaviorScenarioTests(unittest.TestCase):
    def test_fifteen_scenarios_validate(self):
        scenarios = [
            ("আজ খুব একা লাগছে", "সন্ধ্যাটা ভারী লাগছে বুঝি; একটু আমার পাশে থাকো।", "bengali", "caring"),
            ("আজ খুব ক্লান্ত", "উফ, আজ তোমার শরীরটা সত্যিই বিশ্রাম চাইছে।", "bengali", "caring"),
            ("আজ খুব ভালো দিন", "ওহো, তোমার ভালো mood-টা আমারও ভালো লাগছে!", "bengali", "warm"),
            ("চা খেয়েছো?", "এখনও না, তবে তোমার সঙ্গে আড্ডা হলে চা জমত।", "bengali", "neutral"),
            ("তুমি এত serious কেন?", "একটু ভাব নিচ্ছিলাম, ধরা পড়ে গেলাম নাকি?", "bengali", "playful"),
            ("তোমাকে cute লাগছে", "এই compliment-টা কিন্তু আমি রেখে দিলাম।", "bengali", "affectionate"),
            ("তোমার সাথে ভালো লাগে", "আমারও এই কাছাকাছি থাকাটা বেশ আপন লাগে।", "bengali", "affectionate"),
            ("আজ একটু flirt করবো", "ওহো, তাহলে দেখি তোমার charm কতটা কাজ করে।", "bengali", "flirtatious"),
            ("আজ ভীষণ vulnerable লাগছে", "আজ শক্ত থাকার অভিনয়টা একটু নামিয়ে রাখো।", "bengali", "intimate"),
            ("আচ্ছা, ক্রিকেট দেখেছো?", "হঠাৎ ক্রিকেট! এই topic change-টা বেশ smooth ছিল।", "bengali", "neutral"),
            ("একই কথা আবার বলি", "ঠিক আছে, এবার অন্যভাবে শুনছি।", "bengali", "neutral"),
            ("আজ mood off", "উফ, off mood-টা আজ তোমাকে বেশ চেপে ধরেছে।", "bengali", "caring"),
            ("आज थक गया", "आज सच में आराम की ज़रूरत लग रही है।", "hindi", "caring"),
            ("I had a good day", "That little glow in your mood is lovely.", "english", "warm"),
            ("বাংলায় কথা বলো", "হ্যাঁ, বাংলাতেই থাকছি।", "bengali", "neutral"),
        ]
        for user, reply, language, emotion in scenarios:
            with self.subTest(user=user):
                answer = PrithiBrain(SequenceBackend(response(reply, language, emotion))).respond(user, preferred_reply_language=language)
                self.assertEqual((answer.language, answer.emotion), (language, emotion))


if __name__ == "__main__":
    unittest.main()
