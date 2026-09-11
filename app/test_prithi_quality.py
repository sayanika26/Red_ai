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
