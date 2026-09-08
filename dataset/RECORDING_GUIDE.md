# Prithi Dataset Recording Guide

This first dataset uses one spoken sentence for each row in `metadata/recording_script_v1.csv`. Follow the same setup for every recording so the voice stays consistent.

## Before recording

- Record in a quiet room with doors and windows closed.
- Use the same microphone for every clip.
- Keep the microphone at the same distance and angle each time.
- Turn off music, television, fans, and other avoidable background sounds.
- Make sure no other person is speaking nearby.
- Avoid rooms with echo or reverb. Soft furnishings can help reduce reflections.

## How to speak

- Record exactly one sentence per WAV file.
- Read the sentence naturally at a comfortable speaking speed.
- Match the listed emotion gently. Do not exaggerate it.
- Do not whisper, shout, cry, or use a highly dramatic delivery.
- Leave a short pause before and after the sentence, about 0.15 to 0.3 seconds.
- If you make a mistake, record the whole sentence again instead of editing words together.

## File format and naming

- Recommended format: WAV, mono, 24 kHz or 48 kHz.
- Use the exact filename shown in the `audio_filename` column.
- Save Bengali clips in `raw/bengali/`, Hindi clips in `raw/hindi/`, English clips in `raw/english/`, and mixed-language clips in `raw/mixed/`.
- Do not apply effects, compression, equalization, reverb, pitch correction, or noise reduction before uploading.

## Transcript accuracy

The text in the CSV must match every word actually spoken in the WAV file. Do not add, omit, or change words while recording. Punctuation does not need to be spoken, but it should reflect the natural pauses in the recording.

## Marking completed rows

After recording and checking a clip:

1. Confirm that its filename exactly matches the `audio_filename` value.
2. Confirm that the recording contains only the sentence in that row.
3. Change the row's `status` value from `pending` to `completed`.
4. Use the `notes` column for a short factual note if needed, such as `second take` or `minor room noise`.
5. Leave `status` as `pending` when the clip still needs to be recorded or replaced.
