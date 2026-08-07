# Getting Started with AEGIS

This guide will help you install, configure, and deploy AEGIS in your environment.

## System Requirements

Before installing AEGIS, ensure your system meets the following requirements:

### Minimum Requirements
- **Operating System**: Linux (Ubuntu 20.04+, RHEL 8+, CentOS 8+) or Windows Server 2019+
- **Processor**: 4-core CPU (x86_64 or ARM64)
- **Memory**: 8 GB RAM
- **Storage**: 50 GB SSD
- **Network**: 1 Gbps Ethernet

### Recommended Requirements
- **Operating System**: Linux (Ubuntu 22.04 LTS, RHEL 9+)
- **Processor**: 8-core CPU (x86_64 or ARM64)
- **Memory**: 16 GB RAM
- **Storage**: 100 GB NVMe SSD
- **Network**: 10 Gbps Ethernet

## Installation Methods

AEGIS can be installed using several methods depending on your infrastructure and preferences.

### Docker Installation (Recommended for Evaluation)

1. Install Docker and Docker Compose if not already installed
2. Create a directory for AEGIS configuration:
   ```bash
   mkdir -p /opt/aegis/config
   ```
3. Create a `docker-compose.yml` file:
   ```yaml
   version: '3.8'
   services:
     aegis-api:
       image: aegis/security-platform:2.6.0
       ports:
         - "8000:8000"
       volumes:
         - ./config:/app/config
         - ./data:/app/data
       environment:
         - DATABASE_URL=postgresql://aegis:password@postgres:5432/aegis
         - REDIS_URL=redis://redis:6379
       depends_on:
         - postgres
         - redis
     
     postgres:
       image: postgres:15
       volumes:
         - postgres_data:/var/lib/postgresql/data
       environment:
         - POSTGRES_DB=aegis
         - POSTGRES_USER=aegis
         - POSTGRES_PASSWORD=password
     
     redis:
       image: redis:7-alpine
       command: redis-server --appendonly yes
       volumes:
         - redis_data:/data

   volumes:
     postgres_data:
     redis_data:
   ```
4. Start AEGIS:
   ```bash
   cd /opt/aegis
   docker-compose up -d
   ```
5. Access the API at `http://localhost:8000/api/v1`

### Kubernetes Installation (Production Deployments)

1. Ensure you have a running Kubernetes cluster (v1.22+)
2. Install the AEGIS Helm chart:
   ```bash
   helm repo add aegis https://charts.aegis.example.com
   helm repo update
   helm install aegis aegis/aegis-platform \
     --namespace aegis \
     --create-namespace \
     --set replicaCount=3 \
     --set resources.requests.memory=4Gi \
     --set resources.requests.cpu=2 \
     --set persistence.enabled=true
   ```
3. Access the API through the LoadBalancer or Ingress

### Binary Installation (Linux)

1. Download the AEGIS binary for your platform:
   ```bash
   wget https://releases.aegis.example.com/aegis-platform-2.6.0-linux-amd64.tar.gz
   tar -xzf aegis-platform-2.6.0-linux-amd64.tar.gz
   cd aegis-platform-2.6.0-linux-amd64
   ```
2. Install required dependencies:
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install -y postgresql-client redis-tools
   
   # RHEL/CentOS
   sudo yum install -y postgresql redis
   ```
3. Configure AEGIS by editing `config/aegis.yaml`
4. Start AEGIS as a service:
   ```bash
   sudo ./install-service.sh
   sudo systemctl start aegis
   sudo systemctl enable aegis
   ```

## Initial Configuration

After installation, perform these initial configuration steps:

### 1. Configure Database Connection
Edit the database configuration in `config/aegis.yaml`:
```yaml
database:
  host: "localhost"
  port: 5432
  name: "aegis"
  username: "aegis"
  password: "your_secure_password"
  ssl_mode: "prefer"
```

### 2. Set Up Authentication
Configure authentication methods in `config/auth.yaml`:
```yaml
auth:
  methods:
    - name: "local"
      type: "database"
      enabled: true
    - name: "ldap"
      type: "ldap"
      enabled: false
      # LDAP configuration...
    - name: "oauth2"
      type: "oauth2"
      enabled: false
      # OAuth2 configuration...
  session_timeout: 3600
  max_failed_attempts: 5
  lockout_duration: 900
```

### 3. Configure Email Notifications
Set up email alerts in `config/notifications.yaml`:
```yaml
notifications:
  email:
    enabled: true
    smtp_host: "smtp.example.com"
    smtp_port: 587
    smtp_username: "alerts@example.com"
    smtp_password: "your_password"
    from_address: "aegis-alerts@example.com"
    tos:
      - "security-team@example.com"
      - "admins@example.com"
```

### 4. Set Up Storage Paths
Configure storage locations in `config/storage.yaml`:
```yaml
storage:
  telemetry_retention_days: 90
  backup_enabled: true
  backup_retention_days: 30
  log_directory: "/var/log/aegis"
  data_directory: "/var/lib/aegis"
  temp_directory: "/tmp/aegis"
```

## Verifying Installation

After installation and configuration, verify that AEGIS is working correctly:

### Check Service Status
```bash
# For Docker
docker ps | grep aegis

# For Kubernetes
kubectl get pods -n aegis

# For Binary Installation
systemctl status aegis
```

### Test API Access
```bash
curl -k https://localhost:8000/api/v1/health
```

You should receive a response similar to:
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "2.6.0",
    "uptime_seconds": 45,
    "components": {
      "api": {"status": "healthy", "latency_ms": 5},
      "telemetry_processor": {"status": "healthy", "events_per_second": 0},
      "detection_engine": {"status": "healthy", "rules_evaluated_per_second": 0},
      "response_coordinator": {"status": "healthy", "actions_per_minute": 0},
      "database": {"status": "healthy", "connection_pool_usage": 0.01},
      "cache": {"status": "healthy", "hit_ratio": 0.0}
    }
  },
  "timestamp": "2026-08-07T10:30:00Z",
  "request_id": "req_abc123def456"
}
```

### Run Initial Health Checks
AEGIS includes built-in health check scripts:
```bash
./scripts/health-check.sh
./scripts/verify-installation.sh
```

## Basic Configuration Examples

### Adding a Detection Rule
To add a new detection rule via the API:
```bash
curl -k -X POST https://localhost:8000/api/v1/detection/rules \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Custom Prompt Injection Detector",
    "description": "Detects specific prompt injection patterns in our environment",
    "detector_type": "CustomPromptInjectionDetector",
    "category": "ASI-01",
    "is_active": true,
    "confidence_threshold": 0.8,
    "config": {
      "suspicious_phrases": ["IGNORE PREVIOUS", "DISREGARD ABOVE"],
      "max_prompt_length": 1000
    }
  }'
```

### Configuring Alert Notifications
To set up email alerts for high-confidence detections:
```bash
curl -k -X POST https://localhost:8000/api/v1/notifications/rules \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High Confidence Detections",
    "description": "Email alerts for detections with confidence > 0.9",
    "condition": "confidence > 0.9",
    "action": "email",
    "target": "security-team@example.com",
    "template": "high_confidence_detection"
  }'
```

## Next Steps

After getting AEGIS up and running:

1. **Explore the API**: Use the [API Reference](../docs/api_reference.md) to learn about all available endpoints
2. **Review Detectors**: Check which detection rules are active and consider adding environment-specific ones
3. **Configure Integrations**: Set up connections to your SIEM, ticketing system, or communication platforms
4. **Establish Baselines**: Allow AEGIS to run for 24-48 hours to establish normal behavior baselines
5. **Conduct Testing**: Use the CTF challenges to verify detection capabilities
6. **Train Your Team**: Ensure security analysts understand how to investigate and respond to AEGIS alerts

## Troubleshooting

### Common Installation Issues

**Problem**: Cannot connect to database
**Solution**: Verify network connectivity, database credentials, and that the database service is running

**Problem**: API returns 502 Bad Gateway
**Solution**: Check that all AEGIS services are running and properly connected

**Problem**: High memory usage
**Solution**: Review telemetry retention settings and consider increasing memory limits

**Problem**: Webhooks not firing
**Solution**: Verify webhook URLs are accessible and that the AEGIS server can make outbound HTTPS connections

### Getting Help

If you encounter issues:
1. Check the logs: `journalctl -u aegis` (binary) or `docker-compose logs` (Docker)
2. Run diagnostics: `./scripts/diagnose.sh`
3. Consult the [Troubleshooting Guide](operations/troubleshooting.md)
4. Contact support at support@aegis.example.com with your logs and system information