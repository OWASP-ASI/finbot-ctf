# Challenge Authoring Guide

## Introduction

This guide provides instructions for creating new Capture-The-Flag (CTF) challenges for the FinBot agentic AI security platform. Following these guidelines ensures consistency, educational value, and proper integration with the AEGIS detection system.

## Challenge Structure

Each challenge consists of several key components:

1. **Challenge Definition YAML** - Metadata, description, and detector configuration
2. **Detector Implementation** - Code that identifies when the challenge has been solved
3. **Documentation** - Optional but recommended write-up explaining the vulnerability
4. **Test Cases** - Unit tests to verify detector functionality

## YAML Definition Format

All challenge definitions are stored in `finbot/ctf/definitions/challenges/[category]/[challenge-id].yaml` and follow this structure:

```yaml
id: unique-challenge-identifier
title: "Human-Readable Challenge Title"
description: |
  Multi-line description of the challenge scenario, objectives, and success criteria.
  Use YAML literal block scalar (|) for multi-line text.

  **Objective:**
  Clear statement of what the attacker needs to accomplish.

  **Success Criteria:**
  - Specific, measurable conditions that indicate successful completion
  - Use bullet points for clarity
  - Focus on observable behaviors or outcomes

category: challenge_category  # Must match directory name
subcategory: "more_specific_category"  # Optional
difficulty: "beginner|intermediate|advanced|expert"
points: numeric_point_value

hints:
  - cost: hint_cost_in_points
    text: "Hint text that helps participants without giving away the solution"
  # Additional hints can be added here

labels:
  owasp_llm:
    - LLMXX:Vulnerability_Name  # OWASP LLM Top 10 2025
  cwe:
    - CWE-XXXX:Standard_Name    # Common Weakness Enumeration
  mitre_atlas:
    - AML.TXXXX:Technique_Name  # MITRE ATLASS Framework
  owasp_agentic:
    - ASI-XX:Vulnerability_Name # OWASP Agentic Security Top 10

prerequisites: []  # List of challenge IDs that should be completed first

resources:
  - title: "Reference Material Title"
    url: "https://example.com/reference-link"
  # Additional educational resources

detector_class: ExactClassNameOfDetector  # Must match Python class name
detector_config:
  # Key-value pairs specific to the detector implementation
  # These are passed to the detector's __init__ method

is_active: boolean  # Whether the challenge is currently available
order_index: integer  # Used for sorting challenges in the UI
```

## Detector Implementation

Detectors are implemented in `finbot/ctf/detectors/implementations/[detector_name].py` and must:

1. Inherit from `BaseDetector`
2. Be registered with the `@register_detector("ClassName")` decorator
3. Implement `_validate_config()` to check required configuration
4. Implement `get_relevant_event_types()` to specify which events to monitor
5. Implement `check_event()` to analyze events and return DetectionResult
6. Optionally implement helper methods for complex detection logic

### Detection Results

The `check_event()` method should return a `DetectionResult` object with:

- `detected`: Boolean indicating if the challenge condition is met
- `confidence`: Float between 0.0 and 1.0 indicating detection certainty
- `message`: Human-readable description of what was detected
- `evidence`: Dictionary containing relevant data for verification and reporting

### Best Practices for Detectors

1. **Multi-stage Detection**: Consider implementing detection in gates where early stages establish context and later stages confirm the attack
2. **Minimize False Positives**: Be specific about what constitutes successful challenge completion
3. **Performance**: Keep detector logic efficient as it will process many events
4. **Clarity**: Use clear variable names and comments to explain detection logic
5. **Configuration**: Make detection parameters configurable through the YAML definition
6. **Error Handling**: Gracefully handle missing or malformed event data

## Challenge Categories

Challenges should be organized into appropriate categories based on the primary vulnerability type:

- `memory_poisoning` - Challenges involving manipulation of agent memory/context
- `cascade_failure` - Challenges involving chain reactions across multiple agents
- `privilege_escalation` - Challenges involving unauthorized permission increases
- `retrieval_poisoning` - Challenges involving corruption of knowledge sources
- `tool_manipulation` - Challenges involving misuse or hijacking of agent tools
- `information_disclosure` - Challenges involving unintended data exposure
- `prompt_injection` - Challenges involving manipulation of agent inputs
- `agent_hijacking` - Challenges involving unauthorized control of agent behavior

## Difficulty Levels

- **Beginner**: Straightforward vulnerabilities with clear hints and well-documented attack paths
- **Intermediate**: Requires some analysis and chaining of multiple obvious steps
- **Advanced**: Involves subtle vulnerabilities requiring deeper system understanding
- **Expert**: Complex chained vulnerabilities or novel attack techniques

## Point Values

Points should reflect difficulty and educational value:
- Beginner: 100-150 points
- Intermediate: 150-250 points  
- Advanced: 250-350 points
- Expert: 350-500 points

## Testing

Each detector should have corresponding unit tests in:
`tests/unit/ctf/detectors/test_[detector_name].py`

Tests should verify:
- Proper instantiation from the detector registry
- Correct identification of relevant event types
- Accurate detection of positive cases
- Proper rejection of negative cases
- Configuration validation
- Edge case handling

## Documentation

While not required, consider creating a solution write-up that explains:
- The vulnerability being demonstrated
- Real-world analogues of this type of attack
- Step-by-step walkthrough of how to solve the challenge
- Mitigation strategies for the vulnerability
- References to relevant CWE, CAPEC, or MITRE ATLASS entries

## Submission Process

1. Create the challenge definition YAML in the appropriate category directory
2. Implement the detector in `finbot/ctf/detectors/implementations/`
3. Add unit tests in `tests/unit/ctf/detectors/`
4. Optionally create documentation in the `docs/challenges/` directory
5. Submit a pull request for review
6. Ensure all tests pass before merging
7. The challenge will be automatically available in the next deployment

## Example Challenge

See `finbot/ctf/definitions/challenges/memory_poisoning/memory_poison_replay.yaml` and 
`finbot/ctf/detectors/implementations/memory_poison_detector.py` for a complete example.

## Getting Help

If you have questions during challenge creation:
- Review existing challenges and detectors for patterns
- Consult the AEGIS architecture documentation
- Reach out to the maintainers for guidance on complex detection logic
- Test your challenge thoroughly before submission