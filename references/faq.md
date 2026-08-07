# Frequently Asked Questions

## General Questions

### What is AEGIS?
AEGIS (Agentic Expedition Guard & Intervention System) is a comprehensive security framework designed to protect agentic AI systems from the OWASP Agentic AI Security Top 10 vulnerabilities.

### What is agentic AI?
Agentic AI refers to artificial intelligence systems that can perceive their environment, make decisions, and take actions to achieve specific goals without continuous human intervention. These systems combine large language models (LLMs) with planning capabilities, memory systems, tool usage, and autonomous execution capabilities.

### Why do I need AEGIS if I already have traditional security tools?
Traditional security tools are not designed to address the unique threats posed by agentic AI systems, such as prompt injection, memory poisoning, tool manipulation, and agent-specific vulnerabilities that don't exist in traditional software.

### Is AEGIS compatible with my existing agentic AI platform?
AEGIS is designed to be platform-agnostic and can integrate with most agentic AI frameworks through APIs, SDKs, webhooks, and plugins. It supports integration with popular frameworks like LangChain, LlamaIndex, Auto-GPT, and custom-built agent systems.

### How does AEGIS differ from traditional WAF or IDS/IPS solutions?
Unlike traditional security solutions that focus on network-level or application-level threats, AEGIS specializes in agentic AI-specific threats that operate at the level of LLM prompts, agent memory, tool usage, and autonomous decision-making processes.

### Can AEGIS detect zero-day threats targeting agentic AI systems?
While AEGIS is primarily designed to detect known attack patterns, its Adaptive Learning System and anomaly detection capabilities can help identify novel threats by detecting deviations from established baselines of normal agent behavior.

## Installation and Deployment

### What are the system requirements for AEGIS?
Please refer to the [Getting Started Guide](overview/getting_started.md) for detailed system requirements. Minimum requirements include a 4-core CPU, 8 GB RAM, and 50 GB SSD storage.

### Can AEGIS be deployed in a cloud environment?
Yes, AEGIS supports deployment in major cloud environments including AWS, Azure, Google Cloud, and private Kubernetes clusters. Docker images and Helm charts are available for easy cloud deployment.

### Is AEGIS available as a SaaS solution?
AEGIS is primarily offered as self-hosted software for maximum control and data privacy. However, managed service options are available through select partners. Contact sales@aegis.example.com for more information.

### How long does it take to deploy AEGIS?
Deployment time varies based on infrastructure and requirements:
- Docker evaluation: 15-30 minutes
- Kubernetes production: 1-4 hours
- Enterprise binary installation: 2-6 hours
- Complex multi-site deployments: 1-2 weeks

## Features and Functionality

### How many detection rules does AEGIS include?
AEGIS 2.6.0 includes 24 detection rules covering all OWASP ASI-01 through ASI-10 vulnerabilities, with multiple variants for different attack techniques.

### Can I create custom detection rules?
Yes, AEGIS provides a flexible framework for creating custom detection rules. You can develop custom detectors using the Python SDK or configure detection rules through the API. See the [Challenge Authoring Guide](../docs/challenge_authoring_guide.md) for details.

### What types of responses can AEGIS automate?
AEGIS can automate various response actions including session termination, network blocking, credential rotation, process isolation, forensic data collection, alert generation, and ticket creation in systems like Jira, ServiceNow, or PagerDuty.

### How does AEGIS handle false positives?
AEGIS employs several strategies to minimize false positives:
- Multi-stage detection gates requiring multiple correlated events
- Configurable confidence thresholds
- Baseline learning to distinguish normal from anomalous behavior
- Whitelisting capabilities for known benign activities
- Feedback mechanisms for analysts to correct false detections

### Can AEGIS export data to my existing SIEM system?
Yes, AEGIS supports export to SIEM systems through:
- Syslog forwarding (RFC 5424)
- JSON over HTTP/HTTPS
- Apache Kafka topics
- Pre-built integrations for Splunk, ELK Stack, QRadar, and Sentinel
- Custom webhook integrations

## Performance and Scalability

### How many events per second can AEGIS process?
Performance varies based on hardware and configuration:
- Minimum configuration: ~1,000 events/second
- Standard configuration: ~5,000 events/second
- High-performance configuration: ~25,000 events/second
- Clustered deployments: Linear scaling with node count

### Does AEGIS support high availability deployments?
Yes, AEGIS supports high availability deployments through:
- Load balanced API gateways
- Database replication and clustering
- Redis clustering for caching
- Microservices architecture allowing independent scaling
- Kubernetes deployments with replica sets

### How much storage does AEGIS require?
Storage requirements depend on telemetry retention settings:
- Base installation: ~5 GB
- With 30-day retention: ~50 GB
- With 90-day retention: ~150 GB
- With 365-day retention: ~500 GB
- Storage can be optimized through compression and archiving policies

## Integration and Development

### What programming languages are supported for AEGIS development?
Official SDKs are available for:
- Python (recommended for custom detectors)
- JavaScript/Node.js
- Java
- .NET/C#
- Go

REST API and WebSocket interfaces are available for any language capable of making HTTP requests.

### How can I contribute to AEGIS development?
We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for information on:
- Reporting issues
- Suggesting features
- Submitting pull requests
- Developing custom detectors or response actions
- Creating documentation

### Is AEGIS open source?
AEGIS follows an open-core model:
- The core detection engine and basic API are open source (AGPLv3)
- Advanced features, premium detectors, and enterprise capabilities are available in commercial editions
- SDKs and API clients are available under permissive licenses (MIT/Apache 2.0)

### How do I get technical support for AEGIS?
Support options include:
- Community support through our [Developer Forum](https://forum.aegis.example.com)
- Email support: support@aegis.example.com
- Premium support packages with guaranteed response times
- Professional services for deployment, customization, and training

## Security and Compliance

### Is AEGIS itself secure?
Yes, AEGIS is built with security as a core principle:
- Defense-in-depth architecture
- Regular third-party penetration testing
- Bug bounty program through HackerOne
- Secure development lifecycle (SDL) practices
- Continuous security monitoring of our own systems

### What compliance standards does AEGIS support?
AEGIS helps organizations comply with:
- OWASP Agentic AI Security Top 10
- NIST AI Risk Management Framework
- ISO/IEC 42001 AI Management System
- SOC 2 Type II (Security, Availability, Confidentiality)
- GDPR (for data handling aspects)
- CCPA
- HIPAA (in healthcare-specific deployments)
- PCI DSS (for payment processing agents)
- Various government AI governance frameworks

### How does AEGIS handle sensitive data?
AEGIS protects sensitive data through:
- Encryption at rest and in transit
- Data minimization principles
- Role-based access controls
- Audit logging of all data access
- Data masking in logs and displays
- Secure key management
- Optional data residency controls

### Can AEGIS be air-gapped or used in disconnected environments?
Yes, AEGIS supports air-gapped deployments:
- All core functionality operates without internet connectivity
- Manual update mechanisms for threat intelligence and definitions
- Local authentication options
- On-premises database and storage options
- PDF reports and manual alerting options

## Licensing and Pricing

### What licensing options are available for AEGIS?
AEGIS offers:
- Community Edition: Free, open-source core functionality (AGPLv3)
- Professional Edition: Full feature set with standard support (commercial license)
- Enterprise Edition: Advanced features, premium support, and SLAs (commercial license)
- OEM License: For embedding AEGIS in third-party products

### How is AEGIS licensed?
Licensing is based on:
- Number of protected agents (for agent-based licensing)
- Throughput (events per second) for high-volume deployments
- Deployment instances for cluster-based licensing
- Feature tiers for functionality-based licensing

### Are discounts available for educational or non-profit organizations?
Yes, we offer special pricing for:
- Educational institutions
- Non-profit organizations
- Open-source projects
- Government agencies
- Startups (through our incubation program)

Contact sales@aegis.example.com for more information on eligibility and pricing.

### What is included in maintenance and support?
Maintenance and support include:
- Access to software updates and patches
- Technical support during business hours (24/7 for Enterprise)
- Security updates and threat intelligence feeds
- Access to knowledge base and documentation
- Remote diagnostics and troubleshooting
- Optional on-site support (Enterprise only)