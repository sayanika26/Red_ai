import unittest

from prithi_followup import SilenceFollowup


class SilenceFollowupTests(unittest.TestCase):
    def test_sends_at_most_one_gentle_followup(self):
        state = SilenceFollowup()
        state.note_reply("Want to tell me what happened?", "english", now=10)
        self.assertIsNone(state.take_if_due(30, now=39))
        self.assertIsNotNone(state.take_if_due(30, now=40))
        self.assertIsNone(state.take_if_due(30, now=100))

    def test_user_activity_cancels_pending_followup(self):
        state = SilenceFollowup()
        state.note_reply("কী ভাবছো?", "bengali", now=10)
        state.note_user_activity()
        self.assertIsNone(state.take_if_due(30, now=100))

    def test_no_question_never_arms_followup(self):
        state = SilenceFollowup()
        state.note_reply("No rush. I am here.", "english", now=10)
        self.assertIsNone(state.take_if_due(30, now=100))


if __name__ == "__main__":
    unittest.main()
