import json

from prithi_voice import generate_voice


TESTS = (
    {
        "text": "হ্যালো, আজকে তোমার দিনটা কেমন গেল?",
        "language": "bengali",
        "emotion": "neutral",
    },
    {
        "text": "তুমি চাইলে ধীরে ধীরে আমাকে সব বলতে পারো।",
        "language": "bengali",
        "emotion": "caring",
    },
    {
        "text": "अच्छा, आज इतने शांत क्यों हो?",
        "language": "hindi",
        "emotion": "playful",
    },
    {
        "text": "Tell me what happened today. I’m listening.",
        "language": "english",
        "emotion": "warm",
    },
)


def main() -> None:
    results = []
    failures = []
    for index, test in enumerate(TESTS, start=1):
        print(f"\n=== TEST {index} ===")
        try:
            result = generate_voice(**test)
            results.append(result)
        except Exception as exc:
            failure = {
                "test": index,
                **test,
                "error": f"{type(exc).__name__}: {exc}",
            }
            failures.append(failure)
            print("TEST FAILED: " + json.dumps(failure, ensure_ascii=False))

    print("\n=== TEST SUMMARY ===")
    print(f"Successful tests: {len(results)}")
    print(f"Failed tests: {len(failures)}")
    for index, result in enumerate(results, start=1):
        print(
            f"SUCCESS {index}: engine={result['tts_engine']} "
            f"output={result['output_path']} duration={result['duration']:.3f}s "
            f"fallback={result['fallback_occurred']} api_error={result['api_error']}"
        )
    for failure in failures:
        print("FAILED: " + json.dumps(failure, ensure_ascii=False))


if __name__ == "__main__":
    main()
