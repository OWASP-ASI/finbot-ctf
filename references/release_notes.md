# Release Notes

## Version 2.6.0 (August 2026)

### New Features
- **WebSocket API**: Real-time event streaming for telemetry and detection events
- **Enhanced Telemetry Statistics**: Added grouping and aggregation capabilities to telemetry stats endpoint
- **Improved Response Tracking**: Better tracking and reporting of response action executions
- **Component-Level Health Checks**: Enhanced health endpoint with individual component status
- **OpenAPI 3.1.0**: Updated API specification to latest version

### Enhancements
- **Detection Rule Management**: Improved API for creating, updating, and deleting detection rules
- **Pagination Standards**: Standardized pagination across all list endpoints
- **Filtering Capabilities**: Added more filter options to telemetry queries
- **Error Response Consistency**: Improved consistency in error response formats
- **Metrics Endpoint**: Added Prometheus-format metrics endpoint for monitoring

### Bug Fixes
- Fixed issue where detection confidence scores were not being properly normalized
- Resolved memory leak in telemetry processor under high load
- Fixed timezone handling issues in scheduled cleanup jobs
- Resolved race condition in response action execution tracking
- Corrected documentation examples for several API endpoints

### Security Updates
- Updated dependencies to address CVE-2026-XXXX in cryptographic library
- Improved input validation in several API endpoints
- Enhanced session management security
- Updated container images to latest base OS versions

### Known Issues
- WebSocket connections may drop after 24 hours in certain proxy configurations (workaround: implement reconnection logic)
- Occasionally delayed response action execution under extreme system load (mitigation: increase response coordinator resources)
- Unicode characters in agent IDs may cause issues in certain database queries (workaround: use ASCII-compatible agent IDs)

### Deprecations
- None in this release

## Version 2.5.0 (May 2026)

### New Features
- **Pagination Support**: Added limit/offset parameters to all list endpoints
- **Advanced Filtering**: Enhanced filtering capabilities for telemetry queries
- **Detection Rule Templates**: Pre-built templates for common detection scenarios
- **Prometheus Metrics Endpoint**: Added /metrics endpoint for monitoring integration
- **Improved Error Responses**: More detailed and consistent error response formats

### Enhancements
- **API Consistency**: Standardized request/response formats across all endpoints
- **Performance Improvements**: Optimized database queries and indexing strategies
- **Better Logging**: Enhanced structured logging for easier debugging
- **Configuration Validation**: Improved validation of system configuration parameters
- **Health Check Endpoint**: Added basic /health endpoint for load balancer checks

### Bug Fixes
- Fixed issue with large payload handling in telemetry ingestion
- Resolved authentication token expiration handling
- Corrected timezone display in web interface
- Fixed several minor UI issues in the administrative interface
- Corrected documentation examples for detector configuration

### Security Updates
- Updated dependencies to address multiple CVEs in third-party libraries
- Improved password hashing algorithm for stored credentials
- Enhanced protection against timing attacks in authentication
- Updated container security configurations

## Version 2.4.0 (February 2026)

### New Features
- **Advanced Correlation Engine**: Introduced cross-event correlation capabilities for complex attack detection
- **Deception Technology Integration**: Added honeytoken and decoy deployment capabilities
- **Threat Intelligence Feed Integration**: Built-in support for popular threat intelligence feeds
- **Custom Dashboard Builder**: Drag-and-drop interface for creating personalized security dashboards
- **API Versioning**: Formal API versioning scheme with backward compatibility guarantees

### Enhancements
- **Improved Machine Learning Models**: Enhanced adaptive learning algorithms for better detection accuracy
- **Better Resource Management**: Improved resource cleanup and garbage collection
- **Enhanced Documentation**: Expanded API reference with more examples and use cases
- **Improved Installation Scripts**: More robust installation and upgrade procedures
- **Enhanced Notification System**: More flexible notification templates and delivery options

### Bug Fixes
- Fixed memory leak in adaptive learning component under certain conditions
- Resolved issue with detector configuration validation
- Fixed several race conditions in high-concurrency scenarios
- Corrected issues with international character handling in certain fields
- Fixed timezone-related issues in scheduled report generation

### Security Updates
- Updated OpenSSL to address CVE-2026-XXXX
- Improved input sanitization to prevent injection attacks
- Enhanced session fixation protection
- Updated third-party dependencies with known vulnerabilities

## Version 2.3.0 (November 2025)

### New Features
- **Role-Based Access Control (RBAC)**: Fine-grained access control for AEGIS administrative functions
- **Audit Logging**: Comprehensive audit trail of all security-relevant actions within AEGIS
- **Scheduled Reporting**: Automated generation and delivery of security reports
- **Multi-Factor Authentication (MFA)**: Support for TOTP and hardware token-based authentication
- **Service Dependencies**: Ability to define and monitor dependencies between agent services

### Enhancements
- **Improved Detector Performance**: Optimized detector evaluation for reduced latency
- **Better Error Handling**: More graceful degradation under error conditions
- **Enhanced Data Retention**: More flexible data retention policies with archiving options
- **Improved User Experience**: Streamlined administrative interface with better workflows
- **Enhanced Compliance Features**: Additional controls to support regulatory compliance requirements

### Bug Fixes
- Fixed issue with backup restoration procedures
- Resolved deadlock condition under specific concurrent load patterns
- Fixed several UI refresh issues in the web interface
- Corrected issues with LDAP group synchronization
- Fixed timezone handling in report scheduling

### Security Updates
- Updated dependencies to address CVE-2025-XXXX in JSON parsing library
- Improved cryptographic key management practices
- Enhanced protection against XML External Entity (XXE) attacks
- Updated container base images to address OS-level vulnerabilities

## Version 2.2.0 (August 2025)

### New Features
- **External Threat Intelligence**: Ability to ingest and correlate with external threat intelligence feeds
- **Custom Detector Marketplace**: Access to community-developed detectors through integrated marketplace
- **Automated Penetration Testing Integration**: Built-in hooks for automated red teaming tools
- **Incident Case Management**: Integrated case tracking and management for security incidents
- **API Key Rotation**: Automated rotation and management of API keys for integrations

### Enhancements
- **Improved Scalability**: Better horizontal scaling characteristics for large deployments
- **Enhanced Logging Infrastructure**: Improved structured logging with better traceability
- **Better Resource Utilization**: More efficient use of CPU, memory, and disk resources
- **Enhanced Backup and Recovery**: More robust backup procedures with point-in-time recovery options
- **Improved Internationalization**: Better support for multiple languages in user interface

### Bug Fixes
- Fixed issue with high-frequency event processing causing queue buildup
- Resolved several memory leaks in long-running deployments
- Fixed issues with certificate renewal in TLS configurations
- Corrected issues with database connection pooling under stress
- Fixed timezone-related issues in alert scheduling

### Security Updates
- Updated dependencies to fix multiple security vulnerabilities in third-party libraries
- Improved input validation to prevent cross-site scripting (XSS) in admin interface
- Enhanced protection against server-side request forgery (SSRF) attacks
- Updated cryptographic libraries to address known weaknesses

## Version 2.1.0 (May 2025)

### New Features
- **High Availability Clustering**: Official support for clustered deployments with automatic failover
- **Disaster Recovery Tools**: Built-in tools for backup, recovery, and migration between environments
- **Advanced Query Language**: SQL-like syntax for complex telemetry queries and investigations
- **Custom Alert Routing**: Flexible alert routing based on event characteristics and severity
- **Agent Behavior Baseline**: Automatic establishment of normal behavior baselines for anomaly detection

### Enhancements
- **Improved Performance**: Significant performance improvements in telemetry processing and detection evaluation
- **Better Memory Management**: More efficient memory usage and garbage collection
- **Enhanced Documentation**: Expanded API reference with more detailed examples and use cases
- **Improved Error Messages**: More informative error messages to assist in troubleshooting
- **Enhanced Security Monitoring**: Additional internal monitoring for potential security issues within AEGIS itself

### Bug Fixes
- Fixed issue with database schema migrations failing under certain conditions
- Resolved several race conditions in high-concurrency environments
- Fixed issues with log rotation causing file handle exhaustion
- Corrected issues with webhook delivery reliability
- Fixed timezone handling in report generation and scheduling

### Security Updates
- Updated dependencies to address CVE-2025-XXXX in HTTP client library
- Improved protection against brute force attacks on authentication endpoints
- Enhanced session management security
- Updated third-party components with known security issues

## Version 2.0.0 (February 2025)

### Initial Release
- Core AEGIS platform with telemetry collection, detection engine, and response coordinator
- Support for all OWASP ASI-01 through ASI-10 vulnerabilities with initial detector set
- RESTful API for system management and integration
- Basic web-based administrative interface
- Docker images and installation scripts for easy deployment
- Initial set of SDKs for Python and JavaScript
- Basic documentation and getting started guide