# Demo video script: 2:44

Hard limit 3:00; only the first 3:00 is evaluated.

**The sentence this whole video exists to land:**

> **"Nothing failed. But the work no longer fits before the contractual deadline."**

Everything else serves that. If a judge remembers one thing after thirty other agent demos, it is
that sentence.

**Timed, not guessed.** `python scripts/time_script.py` reads this file, counts the narrated
words at 165 wpm, takes the measured execution time declared in each beat, and costs every beat
at `max(talking, waiting)`, because talking over a wait is free, and you cannot talk for forty
seconds over a five second click. Re-run it after any edit to the narration; it has twice caught
a runtime the author had estimated wrong by hand. Current estimate: **2:44, sixteen seconds of
margin.** `--fix-headings` renumbers the beats from those same costs, so the timestamps cannot
drift out of step with the narration.

The riskiest stretch is the agent investigation, beats 4 to 6: it runs about 47 seconds and it
is the only place where the product, not you, sets the pace. Beat 5 exists to spend that wait
rather than stand in it. **The remaining margin is protection, not space to fill**: it absorbs a slow
agent call, a slower delivery of a line, or a scroll that takes a moment. Anything past 3:00 is
simply not evaluated.

## How this script is built

Rules.md scores four **equally weighted** criteria, 25% each. The video is the evidence for all
four, and Potential Impact says explicitly *"based on what's demonstrated"*, so every beat below
is tagged with the criterion it exists to earn. Nothing is here for decoration.

| Beat | Earns |
|---|---|
| 1. The problem, and what missing it costs | Impact: a real audience, a real consequence |
| 2. The miss with zero failures | **Impact**: the strongest thing SLATE has |
| 3. Three detectors disagree | **Impact**: a before/after that changes a decision |
| 4. Agents on real evidence | **Tech**: partner depth, in plain language |
| 5. Drive it yourself, while they run | **Idea**: answers "is this canned?" at zero time cost |
| 6. The diagnosis | **Tech**: the answer came from the evidence, not from us |
| 7. Propose → approve → recover | **Design**: a complete product loop, not a proof of concept |
| 8. Grafana draws, Gemini reads | **Idea**: the non-obvious partner use |
| 9. Close | Trust |

**Two rules that keep this landing.**

1. *The waits are the point, not dead air.* The miss proof takes ~28s and the investigation ~47s.
   Narration over an existing wait is free time, and beat 5 goes further: it does a whole second
   demonstration inside the first one's wait. Do not cut either; the wait is the proof it is
   really running.
2. *Sell the product, do not defend a dissertation.* The repository is exhaustively honest about
   what is simulated and what is not claimed. On camera that is **one sentence**. No more.

---

## Before you hit record

```bash
python scripts/seed_board.py     # fresh contractual dates, three green titles
python scripts/check_page.py     # confirms the page actually initialises
python scripts/time_script.py    # confirms this script still fits
```

Then, **as setup and not on camera**: press **Run 20s judge proof** once and let it finish, then
reload the page.

**What the board will look like when you start recording:** four cards, not three. The board sorts
newest first, so **"Judge proof: premiere package"** sits on top showing `at_risk` and
`codec_fault`, with the three seeded contract titles green underneath. That is correct and
expected: beat 4 needs that card to exist. The opening shot is the headline and the stat tiles,
not the board, so it does not matter that one card is already flagged.

- Browser at 1440×900, zoom 100%, signed out, no extensions visible.
- One tab. Everything in this script is on the one page.
- **Use the navbar, not the scrollbar.** Board, Bring your own, Grafana MCP and Blind spot are one
  click each. Beats 4 to 6 depend on moving quickly while the agents are still working.
- Do a silent dry run first. The buttons are the script.

---

## 0:00–0:16 · The problem, and what missing it costs
<!-- exec: 0 -->

> **DO:** Page at the very top, on the headline and the four stat tiles. Do not scroll, do not
> touch anything.
> **POINT:** The stat tiles: contractual deliveries, and **Never / automatic remediation**.

**"A delivery date in post-production is contractual. Miss it and a release slips. But nobody
finds out they're going to miss it until they miss it, because everything upstream watches for
things breaking, not for whether the work still fits."**

---

## 0:16–0:45 · The miss with zero failures  ← the most important 30 seconds
<!-- exec: 28 -->

> **DO:** Click **Blind spot** in the navbar. Press **Prove it: a miss with zero failures**.
> Then take your hands off the mouse and talk. It runs three waves, about thirty seconds. Do not
> cut them.
> **POINT:** The status line directly under the button as each wave lands. The words you want are
> **0 failures**, and they stay there.

**"So watch this. Eight renditions, a fifty-second window, and I'm injecting no fault at all.
Every encode is going to pass."**

> *Wave 1 lands.*

**"Wave one. Nothing failed. Plenty of window left. Fine."**

> *Wave 2 lands.*

**"Wave two. Still nothing failed. But the work isn't shrinking as fast as the clock is."**

> *Wave 3 lands. Status flips to at risk.*

**"Wave three. Now there is more work left than there is window. Nothing failed, but the work no
longer fits before the deadline."**

> *Read nothing off a rehearsal. The seconds differ every run; the relationship never does.*


---

## 0:45–1:07 · Three detectors, same run
<!-- exec: 2 -->

> **DO:** Nothing at all. When the third wave lands the page scrolls itself to the detector
> comparison, and the green **What the warning buys you** panel renders under it. Keep still.
> **POINT:** The card headed **Invisible miss**, then its three rows top to bottom:
> `any_failure`, `deadline_passed`, `slate_gate`. Then move down to the green panel.

**"Here's what three detectors say about that exact run. A failure alert: silent. Nothing failed.
A deadline check: silent, because the deadline hasn't passed. SLATE fired while there was still
time to act."**

> *Point at the green panel.*

**"And this is what that time is worth. Do nothing, and it misses. Approve one more worker, and
it lands with seconds to spare."**

> *The exact figures change on every run. Read the two the panel actually shows, or say it as
> written above and let the screen supply the numbers. Never quote a rehearsed figure.*


---

## 1:07–1:29 · The agents, on real evidence
<!-- exec: 20 -->

> **DO:** Click **Board** in the navbar. The board is newest first, so the card you just created
> in the miss proof is on top. The one you want is **"Judge proof: premiere package"**, the card
> showing `codec_fault`. Press **Ask ADK agents** on *that* card, then leave it running and keep
> talking. The investigation panel opens directly underneath the board.
> **POINT:** The block headed **"Evidence the agents were bound to"**, and its PromQL, LogQL and
> Tempo rows as they fill in.

**"Now the other half. This one did fail, a missing encoder. Three Google agents investigate it,
and every observation goes through the official Grafana MCP server: the metrics, logs, and trace
for this exact delivery. The diagnosis has to come from that evidence."**

---

## 1:29–1:46 · While it runs: drive it yourself
<!-- exec: 15 -->

> **DO:** The investigation is still running; leave it alone. Click **Bring your own** in the
> navbar. Then click the **your own PromQL** link in that paragraph, click any one of the query
> chips, and press **Run through MCP**.
> **Do not press Load on a preset.** Loading one jumps the page back to the board and you lose
> the beat.
> **POINT:** First the three preset cards and the **"Build your own delivery"** line under them,
> then the raw response that appears below the query box.
>
> *This beat exists because "is it a canned demo?" is the first thing a judge thinks. It costs
> nothing: the investigation is running underneath the whole time.*

**"While that runs. None of this is our fixture. Three presets, and a builder whose rows are the
actual FFmpeg arguments. And your own query goes through the same official MCP server the agents
use. That's the server's raw answer, not ours."**

---

## 1:46–1:59 · The diagnosis
<!-- exec: 12 -->

> **DO:** Click **Board** in the navbar. The investigation has landed underneath it.
> **POINT:** Inside **"Google ADK agents"**, the **Diagnose** block, and the quoted FFmpeg line
> within it.

**"And there it is. It's quoting FFmpeg's actual error, 'Unknown encoder', not an answer we
planted. An earlier build did plant it, scored a hundred percent, and was measuring nothing."**

---

## 1:59–2:13 · Propose, approve, recover
<!-- exec: 10 -->

> **DO:** Stay where you are and move down to the block headed **"Remediate proposed these"**.
> Press **Approve** on the recommended option. Then, on that same delivery card, press
> **Run real pipeline**.
> **POINT:** The schedule cost on each option first, then the status pill on the card turning
> `recovered`.

**"Four actions the system can actually carry out, each costed. The agent recommends, the human
approves, and that approval is what writes the Grafana annotation. Re-run, and the delivery is
recovered before its date."**


---

## 2:13–2:34 · Grafana draws it, Gemini reads it
<!-- exec: 18 -->

> **DO:** Click **Panel read** in the navbar and press **Render the panel through MCP** straight
> away. It takes about seventeen seconds, so do not stand and watch it: click **Grafana MCP** in
> the navbar and deliver the line there. When you finish it, click **Panel read** again.
> **POINT:** In the Grafana MCP section, the four tiles, and specifically **72** and **7**. Then
> back on Panel read, the rendered PNG and Gemini's reading side by side.

**"While that renders, the final receiver is simulated, and the page says so. SLATE uses seven
Grafana MCP tools: metrics, logs, traces, dashboard search, alert rules, annotations and
rendering."**

> *Scroll back down. The PNG and the reading sit side by side.*

**"And there it is. Grafana rendered that panel, MCP carried the image back, and Gemini read the
same chart the supervisor is looking at."**

---

## 2:34–2:43 · Close
<!-- exec: 0 -->

> **DO:** Stay on the panel reading. Do not scroll further.
> **POINT:** Nothing. Let it sit.

**"Apache-2.0, repo and app in the description. SLATE: know a delivery will miss while there's
still time to save it."**


---

## If something fails on camera

Do not re-record from the top. Each of these is recoverable in one sentence:

- **A wave runs slow and the gate opens on wave two.** Say *"there it is, a wave early"* and carry
  on. The point is that it opened with zero failures, not which wave it was.
- **The investigation runs past 47s.** Stay in beat 5 and say one more line about the builder.
  It is the one beat you can stretch, because nothing there is on a clock.
- **The MCP query in beat 5 errors.** Say *"and that is the server's own error text, not ours"*
  and move on. A raw error is still the raw MCP path, which is the point of the beat.
- **You run long.** Cut the list of seven surfaces in beat 8 down to "metrics, logs, traces and
  alerts". That is your slack.
- **The panel render fails.** Say *"that one needs the renderer and it isn't answering, the
  reading is commentary anyway, the gate already decided"*, then go to the close. It costs the
  Idea beat, not the video.

## Shot checklist

- [ ] Opening frame is the headline and the stat tiles, not the board
- [ ] Miss proof pressed live; **failure count visibly zero across all three waves**
- [ ] **"Nothing failed, but the work no longer fits"** said out loud on wave three
- [ ] All three detector rows legible
- [ ] **Green "what the warning buys you" panel on screen, both rows read out**
- [ ] Agent investigation pressed live, not cut
- [ ] **Presets and the ladder builder shown while the agents are still working**
- [ ] **One query run through MCP live, raw response visible**
- [ ] **Quoted FFmpeg stderr legible on screen**
- [ ] Typed remediation options with schedule costs visible
- [ ] Approval pressed on camera, `recovered` shown
- [ ] `7 / 72` tiles and the declines list on screen
- [ ] Rendered PNG shown beside Gemini's reading
- [ ] Simulated receiver stated out loud, once
- [ ] Under 3:00, uploaded **Public**, English audio or subtitles

## Rules compliance for the video itself

- ≤3 minutes, English, public on YouTube or Vimeo, per Rules.md §7B.
- Everything on screen is this app, this Grafana stack, this repository. No third-party footage,
  music, logos or advertising anywhere.
- All media is generated at runtime by FFmpeg from a `lavfi` pattern, so nothing on screen is
  owned by anyone else.
- Show the product *executing*. No slides pretending to be execution.
