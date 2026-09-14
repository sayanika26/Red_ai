import unittest
from unittest.mock import Mock
from prithi_transcript_quality import assess_transcript
from prithi_voice_chat import PrithiVoicePipeline
from prithi_stt import language_code
import test_prithi_web
import json


class QualityTests(unittest.TestCase):
    def test_valid_bengali_and_banglish(self):
        for text in ('আজকে তোমার সাথে কথা বলতে চাই।', 'আজ mood off, একটু কথা বলি।', 'Hello, how are you?'):
            self.assertTrue(assess_transcript({'text':text}, 'bengali')['passed'])

    def test_unrelated_scripts_and_repetition(self):
        for text in ('આજે તમે કેમ છો તમે શું કરો છો', 'আজকে আমি বলি ' * 4, 'Að ég saraði í náin gatsýlu, ekki hún tóngasaði ykktu kotha bóldið jái.'):
            self.assertFalse(assess_transcript({'text':text}, 'bengali')['passed'])

    def test_failed_transcript_preserves_history(self):
        brain, voice = Mock(), Mock()
        pipeline = PrithiVoicePipeline(brain, stt=Mock(return_value={'text':'આજે તમે કેમ છો'}), voice=voice)
        result = pipeline.process_audio('mock.wav', 'bengali')
        self.assertEqual(result['status'], 'STT_EMPTY')
        brain.respond.assert_not_called()
        brain.reset_history.assert_not_called()
        voice.assert_not_called()

    def test_low_confidence(self):
        self.assertFalse(assess_transcript({'text':'test', 'segment_metrics':[{'avg_logprob':-2, 'no_speech_prob':.99}]}, 'english')['passed'])

    def test_bengali_semantic_recovery_uses_context_and_decoder_confidence(self):
        result = {
            'text': 'সেটা শারা দিন কাছে আছে',
            'language_probability': .42,
            'segment_metrics': [{'avg_logprob': -.95, 'no_speech_prob': .55, 'compression_ratio': 1.1}],
        }
        gate = assess_transcript(result, 'bengali', previous_text='আজ অফিসের কাজ নিয়ে খুব চাপ ছিল')
        self.assertFalse(gate['passed'])
        self.assertIn('low_confidence_context_mismatch', gate['reasons'])
        self.assertLess(gate['semantic_confidence'], .58)

    def test_context_change_is_allowed_when_acoustically_confident(self):
        result = {
            'text': 'সেটা আমার খুব ভালো লেগেছে',
            'language_probability': .96,
            'segment_metrics': [{'avg_logprob': -.12, 'no_speech_prob': .01, 'compression_ratio': 1.0}],
        }
        self.assertTrue(assess_transcript(result, 'bengali', previous_text='আজ অফিসে কাজ ছিল')['passed'])

    def test_known_bengali_job_close_homophone_is_rejected(self):
        gate = assess_transcript({'text': 'আজকি শারা দিন অনেক কাছ ছিলো'}, 'bengali')
        self.assertFalse(gate['passed'])
        self.assertIn('known_bengali_semantic_confusion', gate['reasons'])

    def test_language_mapping(self):
        self.assertEqual([language_code(k) for k in ('bengali','hindi','english','auto')], ['bn','hi','en',None])

    def test_stream_observes_actual_routing(self):
        helper = test_prithi_web.PrithiWebTests()
        client, _, _ = helper.make_client()
        helper.prime(client)
        for language, code in [('bengali','bn'),('hindi','hi'),('english','en'),('auto',None)]:
            response = helper.stream_turn(client, language=language)
            first = json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))
            self.assertEqual(first['requested_language'],language)
            self.assertEqual(first['whisper_language'],code)
            self.assertEqual(first['forced'],code is not None)


if __name__ == '__main__':
    unittest.main()
