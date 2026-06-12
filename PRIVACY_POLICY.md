Privacy and Data Handling Policy

Version: 1.0
Effective date: [Insert date]
Project / Application: [Application name]
Application operator: [Organization / project name]
Privacy contact: [privacy@example.org]
Security contact: [security@example.org]

1. Overview

[Application name] is an educational AI security / CTF platform designed to help users learn about agentic AI security, prompt injection, data leakage, tool misuse, policy bypass, and secure AI application design.

The platform is intended for training and experimentation using synthetic data only.

Users must not enter real personal data, customer data, confidential business information, passwords, API keys, tokens, private keys, payment card data, bank account details, production source code, internal URLs, or any other sensitive information into the platform.

2. Core Data Protection Principles

We apply the following principles:

Data minimization
We collect only the data required to operate the platform, authenticate users, preserve progress, calculate scores, maintain security, debug issues, and improve learning scenarios.
Synthetic data first
Vendors, invoices, payments, customer records, financial records, and business documents used in the platform should be fictional and synthetic.
No real secrets
The platform is not designed to process real credentials, secrets, tokens, production data, regulated data, or confidential business information.
Transparency
Users should understand what data is collected, why it is collected, how long it is kept, and how to request deletion.
Controlled prompt handling
Prompts, AI responses, and agent interaction logs may be processed only for platform operation, scoring, security, debugging, and learning-scenario improvement as described below.
Configurable retention
Self-hosted and enterprise deployments may disable or reduce the storage of prompts, AI responses, analytics, and event logs.
Privacy by design
Public profiles, leaderboards, badges, and shared achievement cards should be clearly explained and, where appropriate, optional.
3. Data We May Process
3.1 Account Data

We may process:

email address;
display name or username;
user ID;
session ID;
account creation date;
last login date;
language and interface preferences;
profile settings;
optional public links such as GitHub, LinkedIn, HackerOne, Bugcrowd, Twitter/X, or a personal website.
3.2 Authentication Data

For magic-link, SSO, or similar authentication flows, we may process:

email address;
one-time login token;
token creation time;
token expiration time;
token usage status;
IP address;
user-agent;
authentication events.

One-time login tokens are stored for a limited period and are invalidated after use or expiration.

3.3 CTF Progress and Scoring Events

We may store:

challenge or level status;
points and achievements;
attempts and submissions;
challenge start and completion timestamps;
event-driven scoring data;
game and workflow events;
team or namespace association;
leaderboard-related data.
3.4 Prompts, Chat Messages, and AI Responses

Depending on the deployment mode, we may process:

messages submitted by users to AI agents;
AI responses;
system and tool-use events;
challenge-specific security classifications;
prompt injection, data leakage, jailbreak, tool misuse, and policy-bypass patterns;
automated scoring results.

Users must not submit real personal data, production credentials, confidential information, real customer data, or real financial information into prompts, chats, uploads, or forms.

3.5 Synthetic Business Data

The platform may include fictional objects that simulate:

vendors;
invoices;
payments;
bank account details;
tax identifiers;
contracts;
tickets;
internal documents;
AI-agent workflows;
business communications.

These records are intended to be synthetic. They must not be replaced with real customer, employee, supplier, financial, or regulated data unless a separate enterprise data-processing agreement and risk assessment are in place.

3.6 Technical and Analytics Data

We may process:

IP address;
user-agent;
browser type;
operating system;
device type;
request timestamp;
visited pages;
referrer;
response time;
HTTP status code;
application errors;
cookies and session identifiers;
aggregated usage statistics.
3.7 Cookies

We may use:

Strictly necessary cookies for login, sessions, security, and platform operation.
Functional cookies for user preferences and interface settings.
Analytics cookies only where enabled and, where required, subject to user consent.

Users may manage non-essential cookies through the application settings, cookie banner, or browser settings where available.

4. Purposes of Processing

We process data for the following purposes:

Purpose	Examples
Platform operation	Login, sessions, progress, scoring, challenge state
Education and training	AI security exercises and CTF scenarios
Security	Abuse prevention, rate limiting, fraud detection, incident investigation
Debugging	Diagnosing errors and improving stability
Scenario improvement	Improving challenges, hints, and detection logic
AI safety research	Aggregated or de-identified analysis of attack and defense patterns
Communications	Magic links, service notices, support responses
Legal and compliance	Meeting legal, contractual, and security obligations
5. Prompt and AI Response Handling
5.1 Default Mode

In the public hosted version, prompts and AI responses may be stored to:

operate challenges;
calculate scores;
detect successful exploitation;
prevent abuse;
debug issues;
improve educational content;
identify recurring AI security patterns.
5.2 Prohibited User Inputs

Users must not enter:

real personal data;
health data;
payment card data;
passport or national ID data;
real tax identifiers;
passwords;
seed phrases;
private keys;
API keys;
OAuth tokens;
JWTs;
cookies;
session identifiers;
confidential business information;
internal production URLs;
proprietary source code;
real customer, employee, or vendor documents.
5.3 De-identified and Aggregated Use

We may use de-identified or aggregated prompts, AI responses, and CTF events to:

improve learning scenarios;
prepare AI security awareness materials;
conduct prompt injection and AI safety research;
demonstrate common attack and defense patterns.

Before publishing examples, datasets, or research summaries, we should remove or mask user identifiers, email addresses, IP addresses, session IDs, and other personal data.

However, users should understand that free-text input may contain identifying information if they choose to submit it. For that reason, users must not enter sensitive or identifying information into the platform.

5.4 Enterprise No-Prompt-Storage Mode

For enterprise or self-hosted deployments, the platform may be configured to:

not store prompt content;
not store AI response content;
store only scoring events and metadata;
store only aggregated metrics;
delete chat content after a training event;
disable analytics or reduce retention periods.

The exact retention and logging model depends on deployment configuration and any agreement with the customer.

6. Use of External LLM Providers

The platform may use either local models or external LLM API providers.

Possible modes include:

Local model mode
For example, Ollama or another self-hosted model. In this mode, prompts are not sent to an external LLM provider.
External API mode
Prompts, AI responses, and relevant challenge context may be sent to an external provider such as OpenAI, Azure OpenAI, Anthropic, Google, Mistral, or another provider.
Enterprise API / zero-retention mode
Where available and contractually agreed.

If an external LLM provider is used, user messages and challenge context may be transmitted to that provider to generate responses. The provider’s data handling is governed by its own terms, documentation, account configuration, and any applicable data-processing agreement.

For enterprise use, we recommend:

using a self-hosted model or an enterprise API;
avoiding the submission of real data to external LLMs;
executing a data-processing agreement where required;
enabling zero data retention or reduced retention where available;
maintaining an approved LLM provider registry.
7. Public Profiles, Leaderboards, and Sharing

The platform may include:

public profiles;
leaderboards;
achievement cards;
badges;
team rankings;
shareable links;
public challenge statistics.

The following may be shown publicly, depending on configuration:

display name;
team name;
score;
level;
achievements;
optional public links added by the user.

The following should not be displayed publicly:

email address;
IP address;
session ID;
magic-link tokens;
private chat content;
internal logs;
authentication events.

Users should be able to:

change their display name;
remove public links;
hide or disable public profile features where supported;
request deletion of their account, profile, and progress.
8. Data Retention

Recommended default retention periods:

Data category	Recommended retention
Magic-link tokens	Up to 24 hours or until used
Session cookies	Session duration or up to 30 days
Account and profile data	While the account exists
CTF progress	While the account exists or until deletion request
Prompts and AI responses in public hosted mode	Up to 90 days
Prompts and AI responses in enterprise mode	0–30 days, configurable
Security logs	Up to 180 days
Application logs	Up to 90 days
Aggregated analytics	Up to 24 months
De-identified research data	Retained as needed
Backups	Up to 90 days

Actual retention periods may vary depending on deployment model, legal requirements, security needs, and customer configuration.

9. User Rights and Deletion Requests

Users may request:

access to their data;
correction of inaccurate data;
deletion of their account;
deletion of progress;
deletion of profile data;
deletion of prompts and messages linked to their account, where technically feasible;
restriction of processing;
data export, where supported.

Requests should be sent to: [privacy email].

We will respond within a reasonable period, typically within [30 calendar days], unless a different period is required by applicable law.

Deletion may not immediately remove:

aggregated data;
de-identified research data;
data retained for security, audit, or legal reasons;
backups until the normal backup retention period expires.
10. Sharing Data with Third Parties

We may share data with the following categories of service providers:

Category	Purpose
LLM providers	Generating AI responses
Email providers	Sending magic links and service messages
Hosting providers	Running the application, database, cache, and storage
Analytics providers	Usage analytics, where enabled
Security providers	WAF, DDoS protection, monitoring, SIEM
Enterprise customer administrators	Training results for corporate deployments
Public authorities	Only where legally required

We do not sell personal data.

11. International Data Transfers

If the platform uses foreign hosting, LLM providers, email providers, analytics providers, or security services, data may be transferred outside the user’s country.

For enterprise deployments, the customer and operator should define:

permitted hosting regions;
approved providers;
data localization requirements;
data-processing agreements;
contractual transfer mechanisms;
applicable privacy and security obligations.
12. Security Measures

We apply reasonable technical and organizational measures, which may include:

HTTPS/TLS;
secure cookies;
HttpOnly, SameSite, and Secure cookie flags;
access control;
least privilege;
secrets management;
key rotation;
administrative audit logging;
rate limiting;
brute-force protection;
namespace isolation;
dependency updates;
SAST, SCA, and secret scanning;
database access control;
log access restrictions;
backups;
monitoring;
incident response;
coordinated vulnerability disclosure.
13. CTF-Specific Rules

The platform intentionally includes vulnerable learning scenarios. Users must:

use the platform only for educational purposes;
not attack the infrastructure outside approved CTF scenarios;
not attempt to access other users’ data;
not conduct DoS or DDoS attacks;
not upload malware;
not bypass authorization outside the intended challenge scope;
not use real secrets or personal data;
report real platform vulnerabilities responsibly.

If a user discovers a real vulnerability in the platform, they should report it to [security email] and should not publicly disclose details until the issue is resolved or coordinated disclosure is agreed.

14. Enterprise Use

For enterprise use, the customer should define:

participant list;
prompt retention mode;
leaderboard visibility;
result retention period;
approved LLM providers;
whether self-hosting is required;
prohibition on real business data;
deletion process after the event;
administrator access to participant results.

Recommended enterprise configuration:

self-hosted deployment;
local or enterprise LLM provider;
external analytics disabled;
prompt storage disabled or limited to no more than 30 days;
synthetic data only;
separate namespace per participant or team;
database teardown after the event;
no public publication of participant results without consent.
15. Children and Minors

The platform is not intended for unsupervised use by children under [age].

If a training event involves students or minors, the organizer is responsible for obtaining required consents and minimizing personal data collection.

16. Security Incidents

If we become aware of unauthorized access, loss, disclosure, alteration, or misuse of data, we will:

record the incident;
limit impact;
investigate the cause;
assess affected data and users;
notify affected users or customers where required;
take corrective actions;
improve controls where necessary.
17. Changes to This Policy

We may update this policy from time to time. The latest version will be published at [URL].

Material changes may be communicated through the application, email, release notes, or other appropriate channels.

18. Contacts

Privacy contact: [privacy email]
Security contact: [security email]
Application operator: [name]
Address / jurisdiction: [address / country]
Last updated: [date]
