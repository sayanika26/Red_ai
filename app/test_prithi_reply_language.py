import json
import unittest
from unittest.mock import Mock, patch
from prithi_brain import PrithiBrain, BrainOutputError
from prithi_voice_chat import PrithiVoicePipeline
from prithi_voice import LANGUAGES


def output(language, text):
    return json.dumps({'reply':text, 'language':language, 'emotion':'warm', 'voice_style':{'energy':.5,'warmth':.5,'intimacy':.2,'playfulness':.2,'tenderness':.3,'pace':1.0}})


class ReplyLanguageTests(unittest.TestCase):
    def brain(self, *outputs):
        backend=Mock()
        backend.complete.side_effect=list(outputs)
        return PrithiBrain(backend)

    def check_bn(self, transcript):
        brain=self.brain(output('bengali','হ্যাঁ, তোমার সাথে কথা বলতে ভালো লাগছে।'))
        result=brain.respond(transcript, preferred_reply_language='bengali')
        self.assertEqual(result.language,'bengali')
        self.assertIn('Voice conversation language selected by the user: bengali', str(brain.backend.complete.call_args))

    def test_perfect_bengali(self): self.check_bn('তুমি কি আমার সাথে কথা বলতে রাজি আছো?')
    def test_noisy_bengali(self): self.check_bn('তুমিকি আমার সাথে কথা বলোতে রাজিয় আছে এখন?')
    def test_banglish(self): self.check_bn('আজ mood off, একটু কথা বলি।')

    def test_hindi_output_retries(self):
        brain=self.brain(output('hindi','हाँ, बोलो।'),output('bengali','হ্যাঁ, বলো।'))
        self.assertEqual(brain.respond('কথা বলো',preferred_reply_language='bengali').language,'bengali')
        self.assertEqual(brain.backend.complete.call_count,2)
        self.assertEqual(brain.last_returned_languages,['hindi','bengali'])
        self.assertEqual(brain.history_turn_count,1)

    def test_devanagari_mislabeled_retries(self):
        brain=self.brain(output('bengali','हाँ मैं तुम्हारे साथ बात करूँगी।'),output('bengali','হ্যাঁ, আমি শুনছি।'))
        self.assertEqual(brain.respond('শুনছো?',preferred_reply_language='bengali').reply,'হ্যাঁ, আমি শুনছি।')
        self.assertEqual(brain.backend.complete.call_count,2)

    def test_single_devanagari_word_in_bengali_retries(self):
        brain=self.brain(output('bengali','আচ্ছা, बोलो।'),output('bengali','আচ্ছা, বলো।'))
        self.assertEqual(brain.respond('কথা বলো',preferred_reply_language='bengali').reply,'আচ্ছা, বলো।')
        self.assertEqual(brain.backend.complete.call_count,2)

    def test_hindi_selected(self):
        self.assertEqual(self.brain(output('hindi','हाँ, बोलो।')).respond('hello',preferred_reply_language='hindi').language,'hindi')

    def test_bengali_word_in_hindi_retries(self):
        brain=self.brain(output('hindi','हाँ, কী बात है?'),output('hindi','हाँ, क्या बात है?'))
        self.assertEqual(brain.respond('बताओ',preferred_reply_language='hindi').reply,'हाँ, क्या बात है?')
        self.assertEqual(brain.backend.complete.call_count,2)

    def test_english_selected(self):
        self.assertEqual(self.brain(output('english','I am listening.')).respond('hello',preferred_reply_language='english').language,'english')

    def test_indic_script_in_english_retries(self):
        brain=self.brain(output('english','Okay, বলো.'),output('english','Okay, tell me.'))
        self.assertEqual(brain.respond('hello',preferred_reply_language='english').reply,'Okay, tell me.')
        self.assertEqual(brain.backend.complete.call_count,2)

    def test_auto_inference(self):
        self.assertEqual(self.brain(output('hindi','हाँ, बोलो।')).respond('hello').language,'hindi')

    @patch('prithi_voice_chat.gpu_snapshot', return_value={})
    def test_validated_language_routes_tts(self, _):
        voice=Mock(return_value={'output_path':'mock.wav'})
        brain=self.brain(output('hindi','हाँ।'),output('bengali','হ্যাঁ, বলো।'))
        pipeline=PrithiVoicePipeline(brain, stt=Mock(return_value={'text':'কথা বলো'}),voice=voice)
        result=pipeline.process_audio('mock.wav','bengali')
        self.assertEqual(result['status'],'SUCCESS')
        self.assertEqual(voice.call_args.args[1],'bengali')
        self.assertEqual(LANGUAGES[voice.call_args.args[1]]['gemini_locale'],'bn-BD')

    def test_twice_wrong_never_calls_voice(self):
        voice=Mock()
        brain=self.brain(output('hindi','हाँ।'),output('english','Hello'))
        pipeline=PrithiVoicePipeline(brain, stt=Mock(return_value={'text':'কথা বলো'}),voice=voice)
        result=pipeline.process_audio('mock.wav','bengali')
        self.assertEqual(result['status'],'BRAIN_FAILED')
        voice.assert_not_called()
        self.assertEqual(brain.history_turn_count,0)


if __name__=='__main__': unittest.main()
