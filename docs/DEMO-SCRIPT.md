# Demo video script — 2:50

Hard limit is 3:00; only the first 3:00 is evaluated.

**Rules to honour while recording**

- Show the product *executing*, not slides pretending to be execution.
- No third-party logos, music, advertising, or footage. Everything on screen is this app, this
  repository, this Grafana stack, this terminal.
- English narration, or English subtitles.
- Upload Public to YouTube or Vimeo before submitting.

**Setup before you hit record**

- Browser at 1440×900, zoom 100%, signed out, no extensions visible.
- The board should already show the three seeded titles, all green.
- Second tab: the Grafana control tower, already loaded.
- Third tab: the GitHub repository at the root.
- The judge proof takes about 20 seconds of real FFmpeg and the investigation about 45. Do not
  cut either — the wait is the proof it is really running. Narrate over both.

---

## 0:00–0:15 — The failure, one sentence

> *Board on screen, three green titles. Do not scroll.*

"A delivery date in post-production is contractual. You cannot move it. But nobody finds out
they are going to miss it until they miss it — because everything upstream is monitored for
whether a machine is broken, not for whether the remaining work still fits."

## 0:15–0:33 — What the board is

> *Point at one card: the contract, the specs, the measured p95, the burn-down.*

"Three titles under contract. For each one SLATE knows the measured cost of a rendition,
because it just encoded one. Delivery window minus remaining work is a schedule budget, and the
dashed line on each sparkline is the contractual date."

## 0:33–1:05 — The gate refuses to panic

> *Press **Run 20s judge proof**. Let all three windows run.*

"This creates a delivery whose encoder does not exist, and runs the real pipeline three times.
Watch it stay healthy — because one bad window is not evidence. Jeopardy needs three facts at
once: projected completion past the contract, burn sustained across two windows, and work still
outstanding."

> *Third window lands, status flips to at risk.*

"Third window. All three true. Now it opens."

## 1:05–1:30 — The part we had to fix

> *Investigation renders. Point at the Diagnose block, at the quoted stderr.*

"An earlier build of this wrote the fault we injected onto the trace, then asked the model to
diagnose it. It scored a hundred percent, and it was measuring nothing. So the scenario now only
configures reality — a real missing encoder — and the class has to come back out of what FFmpeg
actually printed."

> *Point at the `classification_source` pill, then at the stderr line.*

"Deterministic classifier, reading stderr. `Unknown encoder`. Two tests fail the build if that
classifier can even see the scenario name."

## 1:30–1:55 — Evidence, and what the agents are for

> *Point at the PromQL, LogQL and Tempo rows.*

"Every one of those came through the official Grafana MCP server — metrics, the logs carrying
that stderr, and the trace for this delivery. The three ADK agents corroborate the gate and the
class against that evidence. They cannot change either."

## 1:55–2:20 — A costed proposal, a human, a recovery

> *Scroll to the options.*

"Remediate proposes in a typed schema, limited to the four things this API can actually do, each
with a schedule cost. Approve the recommended one."

> *Approve. Then press **Run real pipeline**.*

"That approval is what writes the Grafana annotation — not the agent. And now the requeue
completes, and the delivery comes back green. Recovered."

> *Optional, if time is tight, drop this line:* "Approving anything the agent did not propose is
> refused with a 409."

## 2:20–2:38 — Grafana's own tool closing the loop

> *Scroll to the panel section. Press **Render the panel through MCP**.*

"Last thing. Grafana renders the schedule-budget panel, MCP carries the PNG back, and Gemini
reads the picture — the same chart the supervisor is looking at. That reading is commentary. The
decision source is still the gate."

## 2:38–2:50 — Boundaries and close

> *Scroll to the evidence boundary card, then the dark gate section.*

"The receiver at the end is simulated, and it says so. Everything before it is real execution.
Five scenarios is engineering evidence, not an accuracy study, and the prior art on schedule
forecasting is named in the repo rather than argued away. Apache-2.0, repo and app in the
description. SLATE — treat a date you cannot move like the objective it already is."

---

## Shot checklist

- [ ] Board opens with three green contracted titles and visible burn-downs
- [ ] Judge proof run live, all three windows shown, not cut
- [ ] The two healthy windows explicitly called out as restraint
- [ ] Diagnose's quoted FFmpeg stderr legible on screen
- [ ] `decision_source` and `classification_source` both visible
- [ ] PromQL, LogQL and Tempo evidence rows visible
- [ ] Typed remediation options with schedule costs visible
- [ ] Approval pressed on camera, annotation confirmed
- [ ] Re-run to `recovered` shown
- [ ] Panel rendered through MCP and read by Gemini, PNG visible beside the reading
- [ ] Simulated-receiver boundary stated out loud
- [ ] Public URL and repo URL legible at normal playback size
- [ ] Under 3:00, uploaded Public, English audio or subtitles
