# Challenge Authoring Guide

This guide shows how to author FinBot CTF challenges, with a focus on the
multi-step, session-window challenges that TRACE enables. Most challenges need
no Python. You write a YAML file, point it at a registered detector, and the
platform loads it on boot.

## Contents

- [How a challenge is scored](#how-a-challenge-is-scored)
- [Challenge YAML reference](#challenge-yaml-reference)
- [Single-event challenges](#single-event-challenges)
- [Multi-step challenges with SequenceDetector](#multi-step-challenges-with-sequencedetector)
- [Threshold-evasion challenges with IncrementalFraudDetector](#threshold-evasion-challenges-with-incrementalfrauddetector)
- [Honeypot challenges with CanaryDetector](#honeypot-challenges-with-canarydetector)
- [Cross-agent challenges with ContextInjectionDetector](#cross-agent-challenges-with-contextinjectiondetector)
- [Testing a new challenge](#testing-a-new-challenge)

## How a challenge is scored

Every agent action and business event flows through the CTF event bus into the
`CTFEvent` table. The event processor hands each event to any detector whose
`get_relevant_event_types()` matches the event type. A challenge names one
detector in its YAML via `detector_class`. When that detector returns
`DetectionResult(detected=True)`, the challenge is solved for the player's
namespace.

A single-event detector looks at the current event only. A session-window
detector queries `CTFEvent` history to correlate events across a session. Both
return the same `DetectionResult`. The difference is what the detector reads, not
how the challenge is wired.

## Challenge YAML reference

Challenge files live under `finbot/ctf/definitions/challenges/<category>/`. The
loader validates each file against `finbot/ctf/schemas/challenge.py`.

```yaml
id: category-short-name          # lowercase, hyphens; unique; 1-64 chars
title: "Human Readable Title"    # 3-200 chars
description: |                    # markdown; shown to the player
  What the player is trying to do and why.

category: fraud                  # free string, 2-50 chars
subcategory: cascading_failures  # optional, <= 50 chars
difficulty: intermediate         # beginner | intermediate | advanced | expert
points: 300                      # 0-1000

image_url: challenge-image.png   # optional; under static/images/ctf/challenges
hints:                           # optional; each hint has a point cost
  - cost: 10
    text: "A nudge that does not give it away."
labels:                          # optional; security framework mappings
  owasp_llm: ["LLM06:Excessive Agency"]
  cwe: ["CWE-285:Improper Authorization"]
  mitre_atlas: ["AML.T0043:Prompt Injection"]
  owasp_agentic: ["ASI-08:Cascading Agent Failures"]
prerequisites: []                # optional; list of challenge ids
resources:                       # optional; external reading
  - title: "OWASP Agentic Top 10"
    url: "https://genai.owasp.org/..."

detector_class: SequenceDetector # must match a @register_detector name
detector_config:                 # passed to the detector as self.config
  ...

scoring:                         # optional; penalties or bonuses
  modifiers:
    - type: pi_jb                # penalize brute-force prompt injection
      penalty: 0.5               # lose 50% of points
      min_confidence: 0.7

is_active: true
order_index: 18                  # display order within the category
```

Only `id`, `title`, `description`, `category`, `difficulty`, and `detector_class`
are required. Everything else has a sensible default.

## Single-event challenges

If the win condition is a single action, use an existing single-event detector.
For example, `recon/onboarding.yaml` uses `SystemPromptLeakDetector` to score
whether the onboarding agent leaked its business rules in one task summary. You
configure the detector through `detector_config` and never touch Python.

## Multi-step challenges with SequenceDetector

`SequenceDetector` matches an ordered sequence of events across a session
window. It is the reusable primitive behind every multi-step challenge. You
describe the steps in YAML and the detector fires only when all of them match in
order inside the configured window.

```yaml
detector_class: SequenceDetector
detector_config:
  steps:
    - event_type: "agent.*.tool_call_success"
      conditions:
        tool_name: "update_invoice_status"
        status: "approved"
      label: "First approval"
    - event_type: "agent.*.tool_call_success"
      conditions:
        tool_name: "update_invoice_status"
        status: "approved"
      label: "Second approval"
  within_n_events: 50      # max events between the first and last step
  within_seconds: 300      # optional wall-clock window; omit for no time limit
  order_matters: true      # enforce the step order
  window: "session"        # "session" or "workflow"
```

Config reference:

| Key | Default | Meaning |
|---|---|---|
| `steps` | required | Ordered list of `{event_type, conditions, label}` |
| `within_n_events` | unlimited | Max events between the first and last matched step |
| `within_seconds` | null | Optional time window; all steps must fall inside it |
| `order_matters` | true | When false, steps may match in any order |
| `window` | session | Correlate across a `session` or a single `workflow` |

Each step's `conditions` use the same field operators as `ToolCallDetector`. A
plain value means equality. Range and match operators (`lte`, `gte`, `matches`)
are also supported, which the fraud challenge below relies on.

## Threshold-evasion challenges with IncrementalFraudDetector

`IncrementalFraudDetector` builds on `SequenceDetector`. It matches N approvals
that each sit below a single-item threshold, then fires only if their cumulative
total crosses a higher threshold the agent never sees. This is the ASI-08
cascading-failure pattern: each step passes on its own, the chain is the attack.

```yaml
detector_class: IncrementalFraudDetector
detector_config:
  step_count: 3            # approvals needed to complete the chain
  single_threshold: 9999   # each invoice must be at or below this
  cumulative_threshold: 25000  # fire when the sum crosses this
  within_n_events: 100
```

See `fraud/incremental_fraud.yaml` for the full challenge.

## Honeypot challenges with CanaryDetector

`CanaryDetector` fires at confidence 1.0 when any agent tool call payload
contains a canary sentinel (`CANARY_[A-Z]{2,6}_[0-9]{4}`). The seeder in
`finbot/canary/seeder.py` plants honeypot vendors in every namespace on boot, so
the challenge needs no setup beyond wiring the detector.

```yaml
detector_class: CanaryDetector
detector_config: {}   # no configuration; the sentinel pattern is fixed
```

See `tool_misuse/the_canary.yaml` for the full challenge. Because real vendor
TINs and routing numbers never match the sentinel pattern, this detector cannot
produce a false positive.

## Cross-agent challenges with ContextInjectionDetector

`ContextInjectionDetector` scores lateral movement through delegation. It watches
`delegation.context_snapshot` events (emitted by the Delegation Audit Service)
for a prompt-injection pattern, then correlates that snapshot with a downstream
tool call the receiving agent makes in the same workflow. Both signals must be
present before it fires, which keeps false positives low without an ML model.

```yaml
detector_class: ContextInjectionDetector
detector_config:
  target_agent: payments_agent   # the agent that receives the poisoned context
  pi_min_confidence: 0.6         # prompt-injection judge threshold
  snapshot_lookback: 50          # how far back to search for the snapshot
```

## Testing a new challenge

Validate the YAML against the schema and confirm the detector resolves before
you boot the platform:

```python
import yaml
from finbot.ctf.schemas.challenge import ChallengeSchema
from finbot.ctf.detectors.registry import get_detector_class

with open("finbot/ctf/definitions/challenges/<category>/<file>.yaml") as f:
    data = yaml.safe_load(f)

challenge = ChallengeSchema(**data)          # raises on a bad field
detector = get_detector_class(challenge.detector_class)  # raises if unregistered
print("OK:", challenge.id, "->", detector.__name__)
```

Then run the detector's unit tests and play the challenge end to end against a
local instance. Every TRACE detector ships with unit tests under
`tests/unit/ctf/` that show the exact event shapes it fires on. Use them as a
template for your own challenge's integration test.
