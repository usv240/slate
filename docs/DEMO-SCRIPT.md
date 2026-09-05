# Demo video script — 2:47

Hard limit 3:00; only the first 3:00 is evaluated.

**The sentence this whole video exists to land:**

> **"Nothing failed. But the work no longer fits before the contractual deadline."**

Everything else serves that. If a judge remembers one thing after thirty other agent demos, it is
that sentence.

**Timed, not guessed.** `python scripts/time_script.py` reads this file, counts the narrated
words at 165 wpm, takes the measured execution time declared in each beat, and costs every beat
at `max(talking, waiting)` — because talking over a wait is free, and you cannot talk for forty
seconds over a five second click. Re-run it after any edit to the narration.

The riskiest beat is the agent investigation at 47s: it is the only one where the product, not
you, sets the pace.

## How this script is built

Rules.md scores four **equally weighted** criteria, 25% each. The video is the evidence for all
four, and Potential Impact says explicitly *"based on what's demonstrated"* — so every beat below
is tagged with the criterion it exists to earn. Nothing is here for decoration.

| Beat | Earns |
|---|---|
| 1. The problem, and what missing it costs | Impact — a real audience, a real consequence |
| 2. The miss with zero failures | **Impact** — the strongest thing SLATE has |
| 3. Three detectors disagree | **Impact** — a before/after that changes a decision |
| 4. Agents on real evidence | **Tech** — partner depth, in plain language |
| 5. Propose → approve → recover | **Design** — a complete product loop, not a proof of concept |
| 6. Grafana draws, Gemini reads | **Idea** — the non-obvious partner use |
| 7. Close | Trust |

**Two rules that keep this landing.**

1. *The waits are the point, not dead air.* The miss proof takes ~28s and the investigation ~47s.
   Narration over an existing wait is free time. Do not cut either; the wait is the proof it is
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

Then, **as setup and not on camera**: press **Run 20s judge proof** once and let it finish. That
leaves one `at_risk` codec-fault delivery on the board, which beat 4 uses. Reload the page
afterwards so the recording opens clean.

- Browser at 1440×900, zoom 100%, signed out, no extensions visible.
- One tab. Everything in this script is on the one page.
- Do a silent dry run first. The buttons are the script.

---

## 0:00–0:19 · The problem, and what missing it costs
<!-- exec: 0 -->

> **DO:** Board on screen, three green titles. Do not scroll, do not touch anything.
> **POINT:** The contract dates on the three cards.

**"A delivery date in post-production is contractual. Miss it and a release slips, a broadcaster
handoff is missed, a festival slot is gone. But nobody finds out they're going to miss it until
they miss it — because everything upstream watches for things breaking, not for whether the work
still fits."**

*(51 words · 19s)*

---

## 0:19–0:53 · The miss with zero failures  ← the most important 35 seconds
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

**"Wave three. Twenty-eight seconds of work, nineteen seconds of window. Nothing failed — but the
work no longer fits before the deadline."**

*(88 words · 32s, over ~28s of real encoding)*

---

## 0:53–1:10 · Three detectors, same run
<!-- exec: 2 -->

> **DO:** The comparison renders underneath on its own.
> **POINT:** Each row in turn — `any_failure`, then `deadline_passed`, then `slate_gate`.

**"Here's what three detectors say about that exact run. A failure alert: silent — nothing failed,
and it stays silent until the date goes by. A deadline check: silent, and useless. SLATE fired
before the deadline, while there was still time to act. That's the difference."**

*(48 words · 17s)*

---

## 1:10–1:58 · The agents, on real evidence
<!-- exec: 47 -->

> **DO:** Scroll to the board, find the `at_risk` codec-fault delivery, press **Ask ADK agents**.
> Narrate over the wait.
> **POINT:** While it runs — the PromQL, LogQL and Tempo rows as they appear.

**"Now the other half. This one did fail — a missing encoder. Three Google agents investigate it,
and every observation goes through the official Grafana MCP server: the metrics, the logs, and
the trace for this exact delivery. Nothing is summarised from memory."**

> *Investigation lands.*
> **POINT:** The quoted stderr inside the Diagnose block.

**"There. The diagnosis has to come from real evidence — it's quoting FFmpeg's actual error,
'Unknown encoder', not an answer we planted in the scenario. An earlier build of this did plant
it, scored a hundred percent, and was measuring nothing."**

*(85 words · 31s, over ~47s of real agent execution)*

---

## 1:58–2:19 · Propose, approve, recover
<!-- exec: 10 -->

> **DO:** Scroll to the remediation options. Press **Approve** on the recommended one. Then press
> **Run real pipeline** on that delivery.
> **POINT:** The schedule cost on each option, then the status pill flipping to `recovered`.

**"Now SLATE doesn't just raise an alarm. It gives the operator four actions the system can
actually carry out, each with its schedule cost. The agent recommends, the human approves — and
that approval is what writes the Grafana annotation, not the agent. Re-run, and the delivery is
recovered before its date."**

*(53 words · 19s + ~10s of execution)*

---

## 2:19–2:39 · Grafana draws it, Gemini reads it
<!-- exec: 18 -->

> **DO:** Press **Render the panel through MCP** *now*, then immediately scroll up to the
> integration section and talk while it renders (~17s).
> **POINT:** First the `7 / 72` tiles and the declines list. Then scroll back down for the reveal.

**"While that renders — the receiver at the end is simulated, and the page says so. Seven of
seventy-two Grafana tools, and the ones we skipped are listed with the reason. None of this is a
canned path either: every preset downloads as JSON and posts straight back."**

> *Scroll back down. The PNG and the reading sit side by side.*

**"And this: Grafana rendered that panel, MCP carried the PNG back, and Gemini read the chart —
the same picture the supervisor is looking at."**

*(74 words · 27s)*

---

## 2:39–2:47 · Close
<!-- exec: 0 -->

> **DO:** Stay on the panel reading. Do not scroll further.
> **POINT:** Nothing. Let it sit.

**"Apache-2.0, repo and app in the description. SLATE — treat a date you can't move like the
objective it already is."**

*(22 words · 8s)*

---

## If something fails on camera

Do not re-record from the top. Each of these is recoverable in one sentence:

- **A wave runs slow and the gate opens on wave two.** Say *"there it is, a wave early"* and carry
  on. The point is that it opened with zero failures, not which wave it was.
- **The investigation runs past 47s.** Cut the "none of this is a canned path" clause in beat 6.
  That is your slack.
- **The panel render fails.** Say *"that one needs the renderer and it isn't answering — the
  reading is commentary anyway, the gate already decided"*, then go to the close. It costs the
  Idea beat, not the video.

## Shot checklist

- [ ] Board opens with three green contracted titles
- [ ] Miss proof pressed live; **failure count visibly zero across all three waves**
- [ ] **"Nothing failed, but the work no longer fits"** said out loud on wave three
- [ ] All three detector rows legible
- [ ] Agent investigation pressed live, not cut
- [ ] **Quoted FFmpeg stderr legible on screen**
- [ ] Typed remediation options with schedule costs visible
- [ ] Approval pressed on camera, `recovered` shown
- [ ] `7 / 72` tiles and the declines list on screen
- [ ] Rendered PNG shown beside Gemini's reading
- [ ] Simulated receiver stated out loud, once
- [ ] Under 3:00, uploaded **Public**, English audio or subtitles

## Rules compliance for the video itself

- ≤3 minutes, English, public on YouTube or Vimeo — Rules.md §7B.
- Everything on screen is this app, this Grafana stack, this repository. No third-party footage,
  music, logos or advertising anywhere.
- All media is generated at runtime by FFmpeg from a `lavfi` pattern, so nothing on screen is
  owned by anyone else.
- Show the product *executing*. No slides pretending to be execution.
