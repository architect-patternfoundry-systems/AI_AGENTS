# Global Operations Governance

Cross-cutting operational standards for monitoring, logging, and alerting.

## Monitoring Standards

### Prometheus Metrics
All services MUST expose Prometheus metrics on a dedicated port (typically 9100+ range).

**Metric Naming Convention:**
- Use snake_case: `service_name_metric_name`
- Include labels for context: `{status="success", region="us-west"}`
- Use standard metric types: Counter, Gauge, Histogram, Summary

**Required Metrics:**
- `*_requests_total{status}` - Request counts by status
- `*_duration_seconds` - Operation duration histogram
- `*_errors_total{error_type}` - Error counts by type
- `*_health_status` - Health status (1=healthy, 0=unhealthy)

### Health Checks
All services MUST implement health checks:
- `/health/live` - Liveness probe (is the service running?)
- `/health/ready` - Readiness probe (is the service ready to accept traffic?)
- Health checks should be fast (<100ms)
- Health checks should not depend on external services

## Logging Standards

### Log Format
Use structured logging (JSON) with consistent fields:
```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "level": "info",
  "service": "service-name",
  "message": "Human-readable message",
  "context": {
    "request_id": "abc123",
    "user_id": "user456"
  }
}
```

### Log Levels
- `error` - Errors that require immediate attention
- `warn` - Warning conditions that might need attention
- `info` - Informational messages about normal operation
- `debug` - Detailed debugging information (disable in production)

### Log Retention
- Application logs: 30 days
- Audit logs: 90 days minimum
- Security logs: 180 days minimum

## Alerting Standards

### Alert Severity Levels
- **P0 - Critical**: Immediate human intervention required
- **P1 - High**: Response within 15 minutes
- **P2 - Medium**: Response within 1 hour
- **P3 - Low**: Response within 24 hours

### Required Alerts
- Service down (P0)
- High error rate (>5% for 5 minutes) (P1)
- High latency (p95 > 1s for 5 minutes) (P1)
- Disk space >80% (P2)
- Memory usage >85% (P2)

## Deployment Standards

### Deployment Strategy
- Use GitOps (Flux) for infrastructure
- Use rolling updates for application deployments
- Maintain deployment history for rollback capability
- Test in staging before production deployment

### Environment Promotion
- dev → qa → staging → production
- Each environment must have identical configuration
- Promotion requires approval and testing
- Automated rollback on failure detection