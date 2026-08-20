# SLATE evaluation

Run from the project root:

```powershell
$env:FFMPEG_BINARY = "C:\path\to\ffmpeg.exe"
.\.venv\Scripts\python.exe benchmark\run.py
```

The four fault rows come from real FFmpeg executions over a self-authored `lavfi`
fixture. The deadline/burn histories are intentionally constructed evaluation
fixtures. `latest.json` identifies both sources so test data cannot be mistaken
for production telemetry.
