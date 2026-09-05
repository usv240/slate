# Demo video script — 2:51

Hard limit 3:00; only the first 3:00 is evaluated.

**Timed, not guessed.** `python scripts/time_script.py` reads this file, counts the narrated
words at 165 wpm, takes the measured execution time declared in each beat, and costs every beat
at `max(talking, waiting)` — because talking over a wait is free, and you cannot talk for forty
seconds over a five second click. Current estimate: **2:51, nine seconds of margin.** Re-run it
after any edit to the narration.

The riskiest beat is the agent investigation at 47s: it is the only one where the product, not
you, sets the pace. If it runs long, cut the "not our fixture" beat and you are back to 2:37.

## How this script is built

Rules.md scores four **equally weighted** criteria, 25% each. The video is the evidence for all
four, and Potential Impact says explicitly *"based on what's demonstrated"* — so every beat below
is tagged with the criterion it exists to earn. Nothing is here for decoration.

| Beat | Earns |
|---|---|
| 1. The problem | Impact — a real audience with a costly problem |
| 2. The miss with zero failures | **Impact** — the strongest thing SLATE has |
| 3. Three detectors disagree | **Impact** — a before/after that changes a decision |
| 4. Agents on real evidence | **Tech** — partner depth, and the non-circularity fix |
| 5. Approve → recovered | **Design** — a complete product loop, not a proof of concept |
| 6. Grafana draws, Gemini reads | **Idea** — the non-obvious partner use |
| 7. Boundaries and close | Trust — a judge who finds a weakness you already named trusts the rest |

**The two waits are the point, not dead air.** The miss proof takes ~30s and the investigation
~45s. Narration spoken over an existing wait is free time, and that is where half this script
lives. Do not cut either wait; the wait is the proof it is really running.

---

## Before you hit record

```bash
python scripts/seed_board.py     # fresh contractual dates, three green titles
python scripts/check_page.py     # confirms the page actually initialises
```

Then, **as setup and not on camera**: press **Run 20s judge proof** once and let it finish. That
leaves one `at_risk` codec-fault delivery on the board, which beat 4 uses. Reload the page
afterwards so the recording opens clean.

- Browser at 1440×900, zoom 100%, signed out, no extensions visible.
- One tab. Everything in this script is on the one page.
- Do a silent dry run first. The buttons are the script.

---

## 0:00–0:12 · The problem
<!-- exec: 0 -->

> **DO:** Board on screen, three green titles. Do not scroll, do not touch anything.
> **POINT:** The contract dates on the three cards.

**"A delivery date in post-production is contractual. You can't move it. But nobody finds out
they're going to miss it until they miss it — because everything upstream watches for things
breaking, not for whether the work still fits."**

*(38 words · 14s)*

---

## 0:12–0:52 · The miss with zero failures  ← the most important 40 seconds
<!-- exec: 28 -->

> **DO:** Scroll to **"What a failure alert cannot see"**, press **Prove it: a miss with zero
> failures**. Then keep talking. Do not cut the waves.
> **POINT:** The failure count as each wave lands. It stays at zero.

**"So watch this. Eight renditions, a fifty-second window, and I'm injecting no fault at all.
Every encode is going to pass."**

> *Wave 1 lands.*

**"Wave one. Nothing failed. Thirty-five seconds of work left, forty-three of window. Fine."**

> *Wave 2 lands.*

**"Wave two. Still nothing failed. But the work isn't shrinking as fast as the clock is."**

> *Wave 3 lands. Status flips to at risk.*

**"Wave three. Twenty-eight seconds of work, nineteen seconds of window. That delivery is now
going to miss its date — and not one thing has broken."**

*(90 words · 33s, spread across ~40s of real encoding)*

---

## 0:52–1:10 · Three detectors, same run
<!-- exec: 2 -->

> **DO:** The comparison renders underneath on its own.
> **POINT:** Each row in turn — `any_failure`, then `deadline_passed`, then `slate_gate` and its
> lead time.

**"Here's what three detectors say about that exact run. A failure alert: silent — nothing
failed, and it stays silent until the date goes by. A deadline check: silent. Ours fired nineteen
seconds before the date. That's the whole product."**

*(42 words · 15s)*

---

## 1:10–1:54 · The agents, on real evidence
<!-- exec: 47 -->

> **DO:** Scroll to the board, find the `at_risk` codec-fault delivery, press **Ask ADK agents**.
> Narrate over the wait.
> **POINT:** While it runs — the PromQL, LogQL and Tempo rows as they appear.

**"Now the other half. This delivery did fail — a missing encoder. Three Google ADK agents on
Gemini, and every observation goes through the official Grafana MCP server. Metrics, logs,
traces."**

> *Investigation lands.*
> **POINT:** The quoted stderr inside the Diagnose block.

**"There. Diagnose is quoting FFmpeg's actual stderr — 'Unknown encoder'. An earlier build of
this wrote the fault we injected onto the trace and asked the model to diagnose it. It scored a
hundred percent and measured nothing. Now a deterministic classifier reads stderr, and two tests
fail the build if it can even see the scenario name."**

*(100 words · 36s, over ~45s of real agent execution)*

---

## 1:54–2:16 · A costed proposal, a human, a recovery
<!-- exec: 10 -->

> **DO:** Scroll to the remediation options. Press **Approve** on the recommended one. Then press
> **Run real pipeline** on that delivery.
> **POINT:** The schedule cost on each option, then the status pill flipping to `recovered`.

**"Remediate proposes in a typed schema — only the four things this API can actually do, each one
costed. I approve one. That approval is what writes the Grafana annotation, not the agent.
Re-run, and it's recovered."**

*(38 words · 14s + ~8s of execution)*

---

## 2:16–2:29 · It is not our fixture
<!-- exec: 0 -->

> **DO:** Scroll up to the preset cards. Hover the **JSON ↓** button on one of them.
> **POINT:** The three preset cards, then the **Build your own delivery** row beneath them.

**"And none of this is a canned path. Every preset downloads as JSON and posts straight back to
the same endpoint. You can build your own rendition ladder, and run your own PromQL through the
same MCP server."**

*(38 words · 14s — this is the first beat to cut if you are running long)*

---

## 2:29–2:52 · Grafana draws it, Gemini reads it
<!-- exec: 18 -->

> **DO:** Press **Render the panel through MCP** *now*, then immediately scroll up to the
> integration section and talk while it renders (~17s).
> **POINT:** First the `7 / 72` tiles and the declines list. Then scroll back down for the reveal.

**"While that renders — the boundaries. The receiver at the end is simulated, and the page says
so. Seven of seventy-two Grafana tools, and the ones we skipped are listed with the reason."**

> *Scroll back down. The PNG and the reading sit side by side.*

**"And this: Grafana rendered that panel, MCP carried the PNG back, and Gemini read the chart —
the same picture the supervisor is looking at."**

*(60 words · 22s)*

---

## 2:52–3:00 · Close
<!-- exec: 0 -->

> **DO:** Stay on the panel reading. Do not scroll further.
> **POINT:** Nothing. Let it sit.

**"Apache-2.0, repo and app in the description. SLATE — treat a date you can't move like the
objective it already is."**

*(22 words · 8s)*

---

## If something fails on camera

Do not re-record from the top. All three of these are recoverable in one sentence:

- **A wave runs slow and the gate opens on wave two.** Say *"there it is, a wave early"* and carry
  on. The point is that it opened with zero failures, not which wave it was.
- **The investigation runs past 45s.** There is ~20s of slack in beats 6 and 7. Trim the
  boundaries sentence and keep the reveal.
- **You are running long.** Cut the "not our fixture" beat entirely. It is 14 seconds and
  nothing later depends on it.
- **The panel render fails.** Say *"that one needs the renderer and it isn't answering — the
  reading is commentary anyway, the gate already decided"*, then go to the close. It costs the
  Idea beat, not the video.

## Shot checklist

- [ ] Board opens with three green contracted titles
- [ ] Miss proof pressed live; **failure count visibly zero across all three waves**
- [ ] Work-left versus window-left called out on the final wave
- [ ] All three detector rows legible, with the lead time
- [ ] Agent investigation pressed live, not cut
- [ ] **Quoted FFmpeg stderr legible on screen**
- [ ] `decision_source` and `classification_source` visible at least once
- [ ] Typed remediation options with schedule costs visible
- [ ] Approval pressed on camera, `recovered` shown
- [ ] `7 / 72` tiles and the declines list on screen
- [ ] Rendered PNG shown beside Gemini's reading
- [ ] Simulated receiver stated out loud
- [ ] Under 3:00, uploaded **Public**, English audio or subtitles

## Rules compliance for the video itself

- ≤3 minutes, English, public on YouTube or Vimeo — Rules.md §7B.
- Everything on screen is this app, this Grafana stack, this repository. No third-party footage,
  music, logos or advertising anywhere.
- All media is generated at runtime by FFmpeg from a `lavfi` pattern, so nothing on screen is
  owned by anyone else.
- Show the product *executing*. No slides pretending to be execution.
