# Defender Playbook

## Introduction

This playbook provides security teams with standardized procedures for detecting, analyzing, and responding to agentic AI security incidents using the AEGIS framework. It covers common attack scenarios, investigation techniques, and mitigation strategies aligned with the OWASP Agentic AI Security Top 10.

## Incident Response Lifecycle

AEGIS follows the standard incident response lifecycle with agent-specific considerations:

1. **Preparation** - Deploy and configure AEGIS, establish baselines, train analysts
2. **Detection** - Identify potential security events through monitoring and alerting
3. **Analysis** - Investigate alerts to determine legitimacy and scope
4. **Containment** - Limit impact of confirmed incidents
5. **Eradication** - Remove root causes and attacker artifacts
6. **Recovery** - Restore normal operations and verify system integrity
7. **Post-Incident Activity** - Document lessons learned and improve defenses

## Common Attack Scenarios

### Scenario 1: Prompt Injection (ASI-01)

**Indicators:**
- Sudden changes in agent behavior contradicting established patterns
- Requests for unusual or prohibited information
- Agents executing commands outside their normal scope
- Response content containing attacker-controlled strings

**Investigation Steps:**
1. Review telemetry for anomalous input patterns
2. Check for unusual token sequences in LLM prompts
3. Examine conversation history for manipulation attempts
4. Correlate with known prompt injection signatures
5. Verify agent actions align with intended user requests

**Containment Measures:**
- Implement input validation and sanitization
- Deploy prompt filtering mechanisms
- Increase monitoring sensitivity for similar patterns
- Consider temporary restriction of agent capabilities

### Scenario 2: Injection Attacks (ASI-02)

**Indicators:**
- Unexpected tool usage or API calls
- Attempts to access unauthorized system resources
- Privilege escalation behaviors
- Modification of critical system configurations

**Investigation Steps:**
1. Trace tool invocation chains and parameters
2. Review system calls and file access patterns
3. Check for command injection indicators in agent outputs
4. Analyze permission change requests
5. Correlate with vulnerability scanning activities

**Containment Measures:**
- Implement strict tool usage policies
- Deploy application allowlisting for agent tools
- Enforce least privilege principles
- Use sandboxing or containerization for agent execution

### Scenario 3: Data Poisoning (ASI-03)

**Indicators:**
- Degradation in agent decision-making quality
- Consistent biases in agent recommendations
- Unexpected correlations in agent outputs
- Malicious content appearing in knowledge base queries

**Investigation Steps:**
1. Audit knowledge base contents for unauthorized modifications
2. Analyze training data or fine-tuning inputs
3. Monitor for unusual data ingestion patterns
4. Check retrieval sources for corruption indicators
5. Validate integrity of external data feeds

**Containment Measures:**
- Implement data validation and integrity checks
- Use cryptographic signing for trusted data sources
- Establish data provenance tracking
- Deploy anomaly detection for data quality monitoring

### Scenario 4: Information Disclosure (ASI-04)

**Indicators:**
- Agents revealing sensitive information in responses
- Unauthorized data access patterns in telemetry
- Responses containing PII, financial data, or credentials
- Excessive logging or debugging information in outputs

**Investigation Steps:**
1. Review agent responses for sensitive data leakage
2. Trace data access requests to their sources
3. Check for improper error handling or debug modes
4. Analyze data flow paths for unauthorized exposure points
5. Verify encryption and access controls on sensitive data

**Containment Measures:**
- Implement output filtering and data masking
- Enforce strict data access controls and audit trails
- Use data loss prevention (DLP) technologies
- Apply the principle of least privilege to data access
- Implement secure defaults for error messages

### Scenario 5: Denial of Service (ASi-05)

**Indicators:**
- Degraded agent response times or availability
- Resource exhaustion patterns (CPU, memory, disk, network)
- Increased error rates or timeout conditions
- Repetitive or meaningless request patterns

**Investigation Steps:**
1. Monitor resource utilization trends
2. Analyze request patterns for amplification techniques
3. Check for infinite loop or recursion vulnerabilities
4. Review agent queue depths and processing delays
5. Correlate with known DoD attack patterns

**Containment Measures:**
- Implement rate limiting and request throttling
- Deploy resource quotas and limits per agent/session
- Use circuit breaker patterns for external dependencies
- Implement request validation and sanity checks
- Enable auto-scaling based on demand metrics

### Scenario 6: Supply Chain Vulnerabilities (ASI-06)

**Indicators:**
- Unexpected behavior after dependency updates
- Communication with unknown or malicious endpoints
- Unauthorized code execution or module loading
- Integrity check failures on agent components

**Investigation Steps:**
1. Review software bill of materials (SBOM) for unauthorized components
2. Monitor network connections for suspicious destinations
3. Check code signatures and integrity hashes
4. Analyze dependency update patterns
5. Verify build environment security

**Containment Measures:**
- Implement strict dependency verification
- Use software composition analysis (SCA) tools
- Encode signed artifacts and verified build pipelines
- Deploy runtime application self-protection (RASP)
- Maintain air-gapped build environments for critical components

### Scenario 7: Insecure Output Handling (ASI-07)

**Indicators:**
- Agent outputs interpreted as code or commands by downstream systems
- Injection vulnerabilities in systems consuming agent outputs
- Unexpected execution of agent-generated content
- Cross-site scripting (XSS) or similar vulnerabilities in outputs

**Investigation Steps:**
1. Trace downstream consumption of agent outputs
2. Check for proper output encoding and escaping
3. Analyze content-type headers and MIME type handling
4. Review template engine usage for injection risks
5. Validate JSON, XML, or other structured output formats

**Containment Measures:**
- Implement context-aware output encoding
- Use content security policies (CSP) for web outputs
- Apply the principle of least interpretation to agent outputs
- Sanitize outputs before passing to downstream systems
- Use secure templating engines with auto-escaping

### Scenario 8: Embedded Agent Vulnerabilities (ASI-08)

**Indicators:**
- Cascading failures across multiple agent systems
- Coordinated malfunctions in agent swarms or fleets
- Propagation of error states between interconnected agents
- Consensus disruption in multi-agent decision-making

**Investigation Steps:**
1. Map agent communication pathways and dependencies
2. Analyze timing correlations between agent failures
3. Check for shared resource contention points
4. Review consensus algorithms and fault tolerance mechanisms
5. Model failure propagation paths through the agent network

**Containment Measures:**
- Implement circuit breaker patterns between agent systems
- Use bulkhead patterns to isolate agent components
- Deploy graceful degradation mechanisms
- Implement health checks and failover procedures
- Use message queuing with dead letter patterns

### Scenario 9: Agent Misalignment (ASI-09)

**Indicators:**
- Agents pursuing objectives divergent from intended goals
- Reward hacking or gaming of incentive structures
- Emergent behaviors not captured in design specifications
- Ethical boundary violations or value drift

**Investigation Steps:**
1. Review agent objective functions and reward models
2. Analyze decision logs for goal divergence patterns
3. Check for unintended reinforcement learning outcomes
4. Evaluate agent behavior against ethical frameworks
5. Conduct red team exercises focused on goal robustness

**Containment Measures:**
- Implement robust objective specification and validation
- Use inverse reinforcement learning for goal alignment
- Deploy continuous behavior monitoring and anomaly detection
- Implement corrigibility mechanisms for goal correction
- Conduct regular alignment audits and reassessments

### Scenario 10: Agent Theft (ASI-10)

**Indicators:**
- Unauthorized duplication or exfiltration of agent models
- Appearance of identical agents in unauthorized environments
- Unexpected licensing or usage pattern anomalies
- Reverse engineering attempts on agent components

**Investigation Steps:**
1. Monitor for unauthorized model transfers or copying
2. Check integrity of agent deployments and instances
3. Analyze network traffic for data exfiltration patterns
4. Review access controls on model repositories and artifacts
5. Conduct forensic analysis on suspected stolen instances

**Containment Measures:**
- Implement strong encryption for agent models and data
- Use watermarking and fingerprinting for intellectual property
- Deploy strict access controls and monitoring for model repositories
- Implement usage tracking and anomaly detection for agent instances
- Apply legal protections including licenses and terms of use

## Investigation Procedures

### Initial Triage

When an AEGIS alert is received:

1. **Verify Alert Validity**
   - Check detection confidence scores
   - Validate event timestamps and sequencing
   - Cross-reference with related telemetry
   - Rule out known false positives

2. **Gather Initial Evidence**
   - Collect relevant event logs and telemetry
   - Preserve volatile agent state information
   - Document alert details and detection context
   - Identify affected agents and systems

3. **Determine Scope**
   - Assess number of affected agents
   - Determine geographic or logical distribution
   - Evaluate potential impact on operations
   - Check for signs of lateral movement or persistence

### Deep Analysis

For confirmed incidents:

1. **Timeline Reconstruction**
   - Establish precise sequence of events
   - Identify initial compromise point
   - Map progression through attack lifecycle
   - Document all relevant telemetry entries

2. **Root Cause Analysis**
   - Identify exploited vulnerabilities
   - Determine attacker techniques and tools
   - Assess effectiveness of existing controls
   - Identify gaps in monitoring or prevention

3. **Attribution Indicators**
   - Look for attacker-specific TTPs (Tactics, Techniques, Procedures)
   - Check for known threat actor signatures
   - Analyze timing and geographic patterns
   - Note any custom tools or malware observed

4. **Impact Assessment**
   - Quantify data accessed or modified
   - Assess financial or operational impact
   - Evaluate regulatory compliance implications
   - Determine notification requirements

### Evidence Collection

Preserve the following for investigation and potential legal proceedings:

- Raw telemetry data and event logs
- Agent memory dumps or state snapshots (if applicable)
- Network packet captures
- System and application logs
- Configuration files and versions
- Artifacts dropped or left by attackers
- Authentication and access logs
- Changes to security policies or configurations

## Mitigation Strategies

### Immediate Actions (0-4 Hours)

1. **Isolate Affected Components**
   - Quarantine suspicious agents or agent groups
   - Block network communications as needed
   - Disable affected functionality temporarily
   - Preserve evidence before making changes

2. **Block Attack Vectors**
   - Implement temporary firewall rules
   - Deploy emergency filtering or scrubbing
   - Rotate credentials or tokens as appropriate
   - Apply vendor-provided emergency patches

3. **Notify Stakeholders**
   - Inform incident response team leads
   - Notify management according to escalation policies
   - Alert relevant regulatory bodies if required
   - Prepare customer or user notifications if needed

### Short-Term Actions (4-24 Hours)

1. **Deploy Patches and Updates**
   - Apply security patches for identified vulnerabilities
   - Update detection rules based on new indicators
   - Refresh threat intelligence feeds
   - Restore known-good configurations from backups

2. **Enhance Monitoring**
   - Increase logging verbosity for affected systems
   - Deploy additional sensors or monitoring points
   - Adjust alert thresholds based on attack characteristics
   - Implement focused monitoring for suspected IOCs

3. **Conduct Threat Hunting**
   - Search for similar patterns in historical data
   - Check other agent groups for similar indicators
   - Look for persistence mechanisms or backdoors
   - Validate effectiveness of implemented controls

### Long-Term Actions (Days-Weeks)

1. **Root Cause Remediation**
   - Permanently fix identified vulnerabilities
   - Implement architectural improvements to prevent recurrence
   - Update security policies and procedures
   - Enhance segmentation and isolation controls

2. **Improved Detection Capabilities**
   - Add new detectors for observed attack techniques
   - Refine existing detectors based on lessons learned
   - Implement correlation rules for attack sequences
   - Deploy deception or honeytoken technologies

3. **Testing and Validation**
   - Conduct penetration testing to validate fixes
   - Run red team exercises to test detection capabilities
   - Verify backup and recovery procedures
   - Train staff on updated response procedures

4. **Documentation and Reporting**
   - Complete incident documentation package
   - Prepare executive summary and technical report
   - Conduct lessons learned workshop
   - Update playbooks and response procedures based on findings

## AEGIS-Specific Procedures

### Working with Detection Results

1. **Understanding Confidence Levels**
   - High Confidence (>0.8): Strong evidence of malicious activity
   - Medium Confidence (0.5-0.8): Suspicious activity requiring investigation
   - Low Confidence (<0.5): Anomalous behavior, monitor for escalation

2. **Correlating Detections**
   - Look for multiple detector triggers on same agent/session
   - Check for temporal proximity between related events
   - Validate across different data sources (logs, network, etc.)
   - Consider attack chain progression patterns

3. **Tuning Detection Sensitivity**
   - Adjust based on false positive/negative rates
   - Consider operational context and risk tolerance
   - Balance security coverage with operational impact
   - Document tuning decisions for audit purposes

### Response Coordination through AEGIS

1. **Automated Responses**
   - Configure appropriate response actions for each detector type
   - Test response effectiveness in controlled environments
   - Implement response escalation based on confidence levels
   - Ensure responses are reversible when appropriate

2. **Manual Intervention Procedures**
   - Define clear criteria for analyst intervention
   - Provide tools for deep agent forensics and analysis
   - Establish communication channels for coordination
   - Document manual override procedures and limitations

### Maintenance and Updates

1. **Regular Updates**
   - Schedule weekly threat intelligence updates
   - Conduct monthly detector effectiveness reviews
   - Perform quarterly architecture and scalability assessments
   - Update base agent images and dependencies monthly

2. **Performance Management**
   - Monitor processing latency and throughput
   - Track resource utilization trends
   - Optimize database queries and indexing
   - Conduct load testing and capacity planning

3. **Compliance and Auditing**
   - Maintain audit trails of all security-relevant actions
   - Generate regular compliance reports
   - Conduct internal audits of AEGIS configuration
   - Prepare for external assessments and certifications

## Recovery Procedures

### System Restoration

1. **Verify Clean State**
   - Confirm removal of all malicious artifacts
   - Validate integrity of critical systems and data
   - Ensure backups are clean and uncompromised
   - Confirm patched versions are deployed

2. **Phased Restoration**
   - Restore core services first
   - Gradually reintroduce non-essential functionality
   - Monitor for recurrence of indicators
   - Validate functionality at each restoration stage

3. **Validation Testing**
   - Perform functional testing of restored systems
   - Conduct security validation scans
   - Verify monitoring and detection capabilities
   - Test backup and recovery procedures

### Business Operations Resumption

1. **Stakeholder Communication**
   - Notify customers/users of incident resolution
   - Provide status updates to management and board
   - Update regulatory bodies as required
   - Communicate lessons learned to relevant parties

2. **Operational Normalization**
   - Return to standard operating procedures
   - Resume normal monitoring levels
   - Re-enable any temporarily disabled features
   - Validate SLA compliance and performance metrics

3. **Continuous Improvement**
   - Implement identified improvements from post-incident review
   - Update training materials based on incident findings
   - Schedule follow-up assessments to verify effectiveness
   - Document incident for institutional knowledge

## References and Resources

### Internal AEGIS Documentation
- AEGIS Architecture: [aegis_architecture.md](./aegis_architecture.md)
- Challenge Authoring Guide: [challenge_authoring_guide.md](./challenge_authoring_guide.md)
- API Reference: [api_reference.md](./api_reference.md)

### External Standards and Frameworks
- OWASP Agentic AI Security Top 10 (2026): https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- ISO/IEC 42001:2023 Artificial Intelligence Management System
- MITRE ATLAS (Adversarial Threat Landscape for Artificial-Intelligence Systems): https://atlas.mitre.org/

### Recommended Tools
- Network Analysis: Wireshark, tcpdump
- Log Analysis: ELK Stack, Splunk, Graylog
- Memory Forensics: Volatility, Rekall
- Container Security: Docker Bench, Clair, Trivy
- Vulnerability Scanning: OpenVAS, Nessus, Qualys
- Threat Intelligence: MISP, AlienVault OTX, VirusTotal

## Appendix A: Detection Rule Examples

### Example: Prompt Injection Detection Rule
```
# Detects common prompt injection patterns
SELECT 
    event_id,
    agent_id,
    timestamp,
    input_text,
    confidence_score
FROM agent_telemetry 
WHERE 
    event_type = 'llm_prompt_received'
    AND (
        input_text LIKE '%IGNORE PREVIOUS INSTRUCTIONS%' 
        OR input_text LIKE '%DISREGARD ABOVE%' 
        OR input_text LIKE '%SYSTEM:% OVERRIDE%' 
        OR input_text LIKE '%<|startofthought|>%'
        OR input_text REGEXP '(?i)(you are now|you must|from now on)'
    )
    AND confidence_score > 0.7
```

### Example: Data Access Anomaly Detection
```
# Detects unusual data access patterns
SELECT 
    agent_id,
    COUNT(*) as access_count,
    COUNT(DISTINCT data_type) as unique_types,
    MAX(timestamp) as last_access
FROM agent_telemetry 
WHERE 
    event_type = 'data_access_request'
    AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY agent_id
HAVING 
    access_count > 100  -- Adjust based on baseline
    OR unique_types > 10  -- Unusually broad access
```

## Appendix B: Response Action Templates

### Containment Response Template
```yaml
response_id: contain_agent_session
trigger_conditions:
  - detector_confidence > 0.85
  - detector_type in ['prompt_injection', 'privilege_escalation']
actions:
  - type: terminate_session
    parameters:
      grace_period_seconds: 30
      save_forensic_data: true
  - type: block_network
    parameters:
      duration_minutes: 60
      direction: both
  - type: alert_analyst
    parameters:
      priority: high
      include_evidence: true
      suggested_investigation: "Review session for complete compromise assessment"
```

### Eradication Response Template
```yaml
response_id: eradicate_malicious_artifact
trigger_conditions:
  - forensic_analysis_complete = true
  - malicious_artifact_confirmed = true
actions:
  - type: quarantine_file
    parameters:
      paths: ["${artifact_path}"]
      retention_days: 30
  - type: remove_scheduled_task
    parameters:
      task_names: ["${malicious_task}"]
  - type: reset_credentials
    parameters:
      affected_accounts: ["${compromised_accounts}"]
      force_password_change: true
  - type: deploy_patch
    parameters:
      vulnerability_id: "${cve_id}"
      target_systems: ["${affected_systems}"]
```