# Restore Google TTS credentials

Keep the service-account JSON outside Git and transfer it through a secure channel.

```bash
cd ~/prithi-voice
mkdir -p secrets
./scripts/restore_secrets_example.sh /secure/path/google-service-account.json
```

The final path is `~/prithi-voice/secrets/google-tts.json` with mode `0600`. Configure this private line in `app/.env`:

```text
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/prithi-voice/secrets/google-tts.json
```

Verify without displaying content:

```bash
test -f secrets/google-tts.json && echo present
stat -c '%a % %n' secrets/google-tts.json
```

Never paste the JSON into logs, source files, `.env.example`, issues, or chat. If it is ever committed or exposed, revoke/rotate the service-account key in Google Cloud; removing it from a later commit is not sufficient.
