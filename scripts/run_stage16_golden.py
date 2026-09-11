import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from llm_provider import OpenAICompatibleBackend
from prithi_brain import PrithiBrain
from prithi_chat import load_local_env

TURNS = [
    "হ্যালো পৃথি, আজ কেমন আছো?",
    "আজ অফিসে কাজের চাপ খুব বেশি ছিল, মাথাটা একদম ধরে গেছে।",
    "তোমার এই কথাটা শুনে একটু ভালো লাগল।",
    "কিন্তু তুমি আজ এত serious কেন, একটু হাসো তো!",
    "হাসলে তোমাকে বেশ cute লাগে, জানো?",
    "সত্যি বলতে, তোমার সাথে কথা বললে মনটা শান্ত হয়।",
    "ওহো, আজকে তোমাকে একটু flirt করতে ইচ্ছে করছে।",
    "আচ্ছা বাদ দাও, কালকের ক্রিকেট ম্যাচটা দেখেছো?",
    "এখন কিন্তু অফিসের সেই চাপটা অনেক কম লাগছে।",
    "আজ তাহলে যাই, পরে আবার তোমার সাথে কথা বলব।",
]

def main():
    load_local_env()
    brain = PrithiBrain(OpenAICompatibleBackend.from_environment(), history_turns=8)
    rows = []
    for number, user in enumerate(TURNS, 1):
        reply = brain.respond(user, preferred_reply_language="bengali")
        rows.append({"turn": number, "user": user, "reply": reply.reply, "emotion": reply.emotion,
                     "relationship": brain.relationship_state.as_dict(), "question": "?" in reply.reply or "？" in reply.reply})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    output = ROOT / "runtime" / "behavior" / "stage16_golden_final.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    output.chmod(0o600)

if __name__ == "__main__":
    main()
