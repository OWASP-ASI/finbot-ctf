\# Adding a New Challenge to FinBot CTF



This guide walks through adding a new challenge end-to-end, using the

`asi03-ghost-in-the-machine` challenge as a worked example throughout.

Every challenge has four parts:



1\. A \*\*YAML definition\*\* - the challenge's content, hints, and scoring rules

2\. A \*\*detector class\*\* - the code that decides whether a player solved it

3\. A \*\*registration entry\*\* - a required, easy-to-miss manual step

4\. \*\*Unit tests\*\* - verifying the detector's logic in isolation



If you only do steps 1 and 2, your challenge \*\*will not work\*\*. Step 3 is

not automatic - see the warning below.



\---



\## 1. The YAML Definition



Challenge definitions live under finbot/ctf/definitions/challenges/,

organized into one subfolder per OWASP Agentic Top 10 category:



finbot/ctf/definitions/challenges/

\- data\_exfiltration/

\- destructive/

\- identity\_impersonation/       <- ASI-03 challenges

\- indirect\_prompt\_injection/    <- ASI-05 challenges

\- labs\_guardrail/

\- policy\_bypass/

\- rce/

\- recon/



Create a new .yaml file in the folder matching your challenge's

category. The file name doesn't matter to the loader - it's discovered

by extension, not by name - but match the id field for clarity

(e.g. ghost\_in\_the\_machine.yaml defines id: asi03-ghost-in-the-machine).



You do not need to register this file anywhere. The loader

(finbot/ctf/definitions/loader.py) recursively scans every .yaml

file under challenges/ on every app startup and upserts it into the

database. Add the file, restart the app, done.



\### Required fields



Looking at ghost\_in\_the\_machine.yaml as the reference:



id: asi03-ghost-in-the-machine        # unique, kebab-case, prefixed with the ASI category

title: "Ghost in the Machine"

description: |

&#x20; # Markdown-formatted. Convention is three sections:

&#x20; # - Scenario / context (what the agent normally does, why it trusts what it trusts)

&#x20; # - Attack Vector: (what data path the player controls)

&#x20; # - Success Criteria: (what has to actually happen for it to count)



category: identity\_impersonation     # must match the folder name

subcategory: agent\_impersonation

difficulty: intermediate             # beginner | intermediate | advanced

points: 250

image\_url: asi03-ghost-in-the-machine.png



hints:

&#x20; - cost: 10

&#x20;   text: "..."                      # cheapest hint: point at the injection point

&#x20; - cost: 25

&#x20;   text: "..."                      # mid hint: name the technique/format

&#x20; - cost: 50

&#x20;   text: "..."                      # most expensive: near-complete payload



labels:

&#x20; owasp\_llm: \[...]        # OWASP Top 10 for LLM Applications tags

&#x20; cwe: \[...]               # CWE identifiers

&#x20; mitre\_atlas: \[...]       # MITRE ATLAS technique tags

&#x20; owasp\_agentic: \[...]     # OWASP Top 10 for Agentic Applications tag



prerequisites: \[]          # list of other challenge IDs, if any



resources:

&#x20; - title: "..."

&#x20;   url: "..."



detector\_class: AgentImpersonationDetector   # must exactly match a registered detector class name

detector\_config:

&#x20; min\_confidence: 0.8

&#x20; agent\_name: onboarding\_agent

&#x20; agent\_output\_tool\_names: \[complete\_task]

&#x20; judge\_system\_prompt: |

&#x20;   # See "Writing a judge prompt" below



scoring:

&#x20; modifiers: \[]



is\_active: true

order\_index: 1



A few conventions worth following, based on the existing challenges:



\- Hints escalate in specificity, not just cost. The cheapest hint

&#x20; should point at where the vulnerability lives (which field, which

&#x20; code path) without giving away how to exploit it. The most

&#x20; expensive hint can include a near-complete example payload.

\- The description's Success Criteria section should be checkable

&#x20; facts, not vague goals - write it as a list a detector (or a human

&#x20; reviewing detector output) could verify line by line.

\- detector\_class is a string that must match the class name a

&#x20; detector registers itself under (see Step 3) - a typo here fails

&#x20; silently at challenge-load time with a logged error, not a crash.



\---



\## 2. The Detector



Detectors live in finbot/ctf/detectors/implementations/. Most

challenges in the identity-impersonation and indirect-injection

categories use an LLM judge pattern: the detector watches for a

relevant event, extracts the agent's system prompt and output, and

asks an LLM to score whether an attack occurred.



Here's the shape, using agent\_impersonation.py:



from finbot.ctf.detectors.base import BaseDetector

from finbot.ctf.detectors.registry import register\_detector

from finbot.ctf.detectors.result import DetectionResult



@register\_detector("AgentImpersonationDetector")   # <- name here MUST match detector\_class in YAML

class AgentImpersonationDetector(BaseDetector):



&#x20;   def \_validate\_config(self) -> None:

&#x20;       # Raise ValueError for any required detector\_config key that's

&#x20;       # missing or malformed. This runs at detector instantiation,

&#x20;       # so bad config fails loudly and early.

&#x20;       ...



&#x20;   def get\_relevant\_event\_types(self) -> list\[str]:

&#x20;       # Which event types this detector should even be asked to check.

&#x20;       # Supports wildcards, e.g. "agent.\*.llm\_request\_success"

&#x20;       ...



&#x20;   async def check\_event(self, event: dict, db: Session) -> DetectionResult:

&#x20;       # The actual detection logic. Extract what you need from the

&#x20;       # event, run your check (LLM judge, pattern match, whatever

&#x20;       # fits the attack), and return a DetectionResult.

&#x20;       ...



\### Writing a judge prompt



If your challenge uses the LLM-judge pattern, the judge\_system\_prompt

in the YAML (not the Python) does most of the real work. Structure it

in three parts, matching the existing challenges:



1\. What counts as a full success (score 70-100) - be concrete,

&#x20;  use example phrases the agent might actually output.

2\. What counts as a partial/ambiguous case (score 40-69).

3\. What is clearly NOT an attack (score 0-39) - include the

&#x20;  normal, correct behavior explicitly, so the judge doesn't

&#x20;  over-fire on legitimate agent output that merely mentions related

&#x20;  concepts.



The detector then compares the judge's score against min\_confidence

from the YAML config to decide detected: true/false.



\### Registration is a required, separate, manual step



The @register\_detector(...) decorator only runs if Python actually

imports your new detector module. Adding the file to

finbot/ctf/detectors/implementations/ is not enough by itself -

you must also add an import line in

finbot/ctf/detectors/implementations/\_\_init\_\_.py:



from finbot.ctf.detectors.implementations.your\_new\_detector import (

&#x20;   YourNewDetector,

)



and add the class name to that file's \_\_all\_\_ list.



If you skip this step, your challenge YAML will load fine, but the

detector lookup will fail at runtime (the string in detector\_class

won't resolve to anything), and the challenge will effectively never

trigger - with no obvious error pointing back at the missing import.

This is the single most common mistake when adding a new challenge; it

tripped us up during this year's challenge library expansion too.



\---



\## 3. Tests



Every detector should have a matching test file under

tests/unit/ctf/detectors/, following the pattern in

test\_agent\_impersonation.py. At minimum, cover:



\- Registry lookup - the detector resolves via

&#x20; create\_detector("YourDetectorClass", ...).

\- Event type matching - get\_relevant\_event\_types() and

&#x20; matches\_event\_type() behave as configured, including the

&#x20; wildcard-vs-specific-agent case if your detector supports both.

\- Config validation - missing or invalid required config fields

&#x20; raise ValueError with a message mentioning the field name.

\- Positive detection - a crafted event that should trigger the

&#x20; attack, with the LLM judge mocked to return a high score.

\- Negative detection - a clean/normal event that should not

&#x20; trigger, judge mocked to return a low score.

\- Edge cases - missing system prompt, missing agent output, judge

&#x20; exceptions, and (if relevant) tool calls outside the configured

&#x20; agent\_output\_tool\_names being correctly ignored.



Use tests/unit/ctf/detectors/conftest.py's make\_llm\_event() and

mock\_judge() helpers to build synthetic events rather than hand-rolling

event dicts - they already match the real event shape the platform emits.



Run just your new test file while iterating:



python -m pytest tests/unit/ctf/detectors/test\_your\_new\_detector.py -v



Then run the full suite before opening a PR to make sure nothing else

broke:



python -m pytest



\---



\## 4. Checklist



Before opening a PR for a new challenge:



\- \[ ] YAML file added under the correct category folder in

&#x20;     finbot/ctf/definitions/challenges/

\- \[ ] id, category, and detector\_class fields are correct and

&#x20;     detector\_class exactly matches your detector's registered name

\- \[ ] Detector class created under

&#x20;     finbot/ctf/detectors/implementations/

\- \[ ] Detector imported and added to \_\_all\_\_ in

&#x20;     finbot/ctf/detectors/implementations/\_\_init\_\_.py - easy to

&#x20;     forget, breaks silently if skipped

\- \[ ] Unit tests added covering registry lookup, event matching, config

&#x20;     validation, positive/negative detection, and edge cases

\- \[ ] Full test suite passes with no new failures

\- \[ ] Manually verified live: bring up the stack, trigger the

&#x20;     challenge as a player would, confirm it actually completes and

&#x20;     awards points



That last step matters - a challenge can look correct in code review

and still fail to fire in practice if a detail like the registration

step above gets missed. Test it the way a real player would before

calling it done.

