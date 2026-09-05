# Resilient Monitoring Template

This template provides a reusable pattern for implementing the AI_AGENTS Resilient Monitoring Philosophy across services.

## Application Template

### Python Service Pattern

```python
"""
Resilient Service Template - Implements graceful recovery and context-aware monitoring
"""

import time
import threading
from collections import deque
from prometheus_client import start_http_server, Counter, Histogram, Gauge

class ResilientService:
    def __init__(self, service_name, dependencies, max_queue_size=100):
        """
        Args:
            service_name: Name of the service for metrics
            dependencies: List of dependency names to monitor
            max_queue_size: Maximum queue size for graceful recovery
        """
        self.service_name = service_name
        self.dependencies = {dep: True for dep in dependencies}
        self.running = True
        self.lock = threading.Lock()
        self.max_queue_size = max_queue_size
        self.queue = deque(maxlen=max_queue_size)
        self.operation_func = None  # Subclass must set this
        
        # Prometheus metrics (following AI_AGENTS operations standards)
        self.setup_metrics()
        
    def setup_metrics(self):
        """Setup Prometheus metrics for resilient monitoring"""
        # Standard metrics
        self.requests_total = Counter(f'{self.service_name}_requests_total', 
                                      'Total requests', ['status'])
        self.duration_seconds = Histogram(f'{self.service_name}_duration_seconds',
                                         'Operation duration')
        self.errors_total = Counter(f'{self.service_name}_errors_total',
                                   'Total errors', ['error_type'])
        self.health_status = Gauge(f'{self.service_name}_health_status',
                                   'Health status (1=healthy, 0=unhealthy)')
        
        # Dependency health metrics (resilient monitoring)
        for dep in self.dependencies:
            self.__dict__[f'{dep}_health'] = Gauge(
                f'{self.service_name}_{dep}_health',
                f'{dep} health status (1=healthy, 0=unhealthy)'
            )
        
        # Recovery metrics
        self.queue_size = Gauge(f'{self.service_name}_queue_size',
                               'Number of items queued for retry')
        self.retry_attempts_total = Counter(f'{self.service_name}_retry_attempts_total',
                                            'Total retry attempts')
        self.downstream_validation_status = Gauge(
            f'{self.service_name}_downstream_validation_status',
            'Downstream pipeline health (1=healthy, 0=unhealthy)'
        )
    
    def check_dependency_health(self, dependency_name, health_check_func):
        """
        Check dependency health with context-aware monitoring
        
        Args:
            dependency_name: Name of the dependency
            health_check_func: Function that returns True if healthy
        """
        try:
            was_healthy = self.dependencies[dependency_name]
            is_healthy = health_check_func()
            self.dependencies[dependency_name] = is_healthy
            
            # Update health metric
            health_metric = self.__dict__[f'{dependency_name}_health']
            health_metric.set(1 if is_healthy else 0)
            
            # Context-aware alerting: only alert on status change
            if not is_healthy and was_healthy:
                self.errors_total.labels(error_type=f'{dependency_name}_unavailable').inc()
                print(f"[ALERT] {dependency_name} unavailable - queuing requests locally")
            elif is_healthy and not was_healthy:
                print(f"[RECOVERY] {dependency_name} recovered - processing queued items")
                self.process_queue_on_recovery(dependency_name)
                
        except Exception as e:
            was_healthy = self.dependencies[dependency_name]
            self.dependencies[dependency_name] = False
            health_metric = self.__dict__[f'{dependency_name}_health']
            health_metric.set(0)
            
            if was_healthy:
                self.errors_total.labels(error_type=f'{dependency_name}_unavailable').inc()
                print(f"[ALERT] {dependency_name} health check failed: {e}")
    
    def process_with_graceful_recovery(self, operation_func, item, dependency_name):
        """
        Execute operation with graceful recovery
        
        Args:
            operation_func: Function to execute
            item: Item to process
            dependency_name: Required dependency
        """
        if not self.dependencies[dependency_name]:
            # Queue item locally, don't alert (context-aware)
            with self.lock:
                if len(self.queue) < self.max_queue_size:
                    self.queue.append(item)
                    self.queue_size.set(len(self.queue))
                    print(f"[QUEUE] Item queued for retry: {item}")
                else:
                    self.errors_total.labels(error_type='queue_full').inc()
            return False
            
        try:
            result = operation_func(item)
            if result:
                return True
            else:
                # Queue for retry, don't alert (dependency issue is root cause)
                with self.lock:
                    if len(self.queue) < self.max_queue_size:
                        self.queue.append(item)
                        self.queue_size.set(len(self.queue))
                return False
        except Exception as e:
            # Queue for retry, don't alert (dependency issue is root cause)
            with self.lock:
                if len(self.queue) < self.max_queue_size:
                    self.queue.append(item)
                    self.queue_size.set(len(self.queue))
            return False
    
    def process_queue_on_recovery(self, dependency_name):
        """Process queued items when dependency recovers (downstream validation)"""
        if not self.dependencies[dependency_name] or not self.queue:
            return
            
        if self.operation_func is None:
            raise NotImplementedError("Subclass must set self.operation_func before processing queue")
            
        print(f"[RECOVERY] Processing {len(self.queue)} queued items...")
        
        with self.lock:
            items_to_process = list(self.queue)
            self.queue.clear()
            self.queue_size.set(0)
        
        success_count = 0
        for item in items_to_process:
            self.retry_attempts_total.inc()
            if self.process_with_graceful_recovery(self.operation_func, item, dependency_name):
                success_count += 1
            else:
                # Re-queue if still failing
                with self.lock:
                    if len(self.queue) < self.max_queue_size:
                        self.queue.append(item)
                        self.queue_size.set(len(self.queue))
        
        print(f"[RECOVERY] Processed {success_count}/{len(items_to_process)} queued items")
        
        # Validate downstream pipeline health
        self.validate_downstream_health()
    
    def validate_downstream_health(self):
        """Check that downstream systems recovered (design feedback)"""
        try:
            # Implement downstream health checks specific to your service
            downstream_healthy = self.check_downstream_health()
            
            self.downstream_validation_status.set(1 if downstream_healthy else 0)
            
            if not downstream_healthy:
                self.errors_total.labels(error_type='downstream_unhealthy_after_recovery').inc()
                print(f"[ALERT] Downstream pipeline unhealthy after recovery - graceful recovery may need improvement")
            else:
                print(f"[VALIDATION] Downstream pipeline healthy after recovery")
                
        except Exception as e:
            self.downstream_validation_status.set(0)
            self.errors_total.labels(error_type='downstream_validation_failed').inc()
            print(f"[ERROR] Downstream validation failed: {e}")
    
    def check_downstream_health(self) -> bool:
        """
        Override in subclass. Return True only if downstream pipeline 
        has actually processed work, not just that it responds to health checks.
        Default raises to force implementation.
        """
        raise NotImplementedError(
            "Subclass must implement check_downstream_health() with real pipeline validation"
        )
```

## Prometheus Alerting Template

### Context-Aware Alert Rules

```yaml
groups:
- name: resilient_monitoring
  rules:
  # Root cause alerts
  - alert: ServiceDependencyUnavailable
    expr: service_dependency_health_status == 0
    for: 5m
    labels:
      severity: P1
      root_cause: "dependency_unavailable"
    annotations:
      summary: "{{ $labels.service }} dependency {{ $labels.dependency }} unavailable - queuing requests locally"
      description: "Service {{ $labels.service }} cannot reach {{ $labels.dependency }}. Requests are being queued locally for retry."
  
  # Symptom alerts (suppressed when root cause known)
  - alert: ServiceOperationErrors
    expr: service_errors_total > 0
    for: 1m
    labels:
      severity: P3
    annotations:
      summary: "{{ $labels.service }} operation errors detected"
    # Suppress if any dependency is down (root cause known)
    # Only alert if errors occur when all dependencies are healthy
    # Implement via alert suppression rules in Prometheus
  
  # Downstream validation alerts
  - alert: ServiceDownstreamUnhealthyAfterRecovery
    expr: service_dependency_health_status == 1 and downstream_validation_status == 0
    for: 5m
    labels:
      severity: P2
    annotations:
      summary: "{{ $labels.service }} downstream pipeline unhealthy after dependency recovery"
      description: "Dependency recovered but downstream pipeline remains unhealthy. Graceful recovery mechanism may need improvement."
  
  # Queue size alerts
  - alert: ServiceQueueSizeHigh
    expr: service_queue_size > 50
    for: 5m
    labels:
      severity: P2
    annotations:
      summary: "{{ $labels.service }} queue size is high"
      description: "Service {{ $labels.service }} has {{ $value }} items queued. Dependency may be down or processing slow."
  
  - alert: ServiceQueueFull
    expr: service_queue_size >= 100
    for: 1m
    labels:
      severity: P1
    annotations:
      summary: "{{ $labels.service }} queue is full"
      description: "Service {{ $labels.service }} queue is full. New items will be dropped."
```

### Alert Suppression Rules (Alertmanager)

```yaml
# Real suppression using inhibit_rules in alertmanager.yml
inhibit_rules:
  # Suppress operation errors when dependency is down
  - source_matchers:
      - alertname="ServiceDependencyUnavailable"
    target_matchers:
      - alertname="ServiceOperationErrors"
    equal: ['service']
  
  # Suppress downstream validation alerts when dependency is down
  - source_matchers:
      - alertname="ServiceDependencyUnavailable"
    target_matchers:
      - alertname="ServiceDownstreamUnhealthyAfterRecovery"
    equal: ['service']
  
  # Suppress queue size alerts when dependency is down (expected behavior)
  - source_matchers:
      - alertname="ServiceDependencyUnavailable"
    target_matchers:
      - alertname="ServiceQueueSizeHigh"
    equal: ['service']
```

### Concrete Example: Podcast Watcher

```yaml
groups:
- name: podcast_watcher_resilient
  rules:
  # Root cause alert
  - alert: PodcastWatcherCTSApiDown
    expr: podcast_watcher_cts_api_health == 0
    for: 5m
    labels:
      severity: P1
      root_cause: "cts_api_unavailable"
    annotations:
      summary: "CTS API is down - uploads queued locally"
      description: "Podcast watcher cannot reach CTS API. Files are being queued locally for retry."
  
  # Symptom alert (suppressed when CTS API is down)
  - alert: PodcastWatcherUploadErrors
    expr: podcast_watcher_errors_total{error_type="upload_failure"} > 0
    for: 1m
    labels:
      severity: P3
    annotations:
      summary: "Podcast watcher upload errors detected"
      description: "Upload failures detected. Will be suppressed if CTS API is down."
  
  # Downstream validation alert
  - alert: PodcastWatcherDownstreamUnhealthyAfterRecovery
    expr: podcast_watcher_cts_api_health == 1 and podcast_watcher_downstream_validation_status == 0
    for: 5m
    labels:
      severity: P2
    annotations:
      summary: "Podcast watcher downstream pipeline unhealthy after CTS recovery"
      description: "CTS API recovered but downstream pipeline remains unhealthy. Graceful recovery may need improvement."
  
  # Queue size alerts
  - alert: PodcastWatcherQueueSizeHigh
    expr: podcast_watcher_queue_size > 50
    for: 5m
    labels:
      severity: P2
    annotations:
      summary: "Podcast watcher queue size is high"
      description: "Podcast watcher has {{ $value }} files queued. CTS API may be down."
  
  - alert: PodcastWatcherQueueFull
    expr: podcast_watcher_queue_size >= 100
    for: 1m
    labels:
      severity: P1
    annotations:
      summary: "Podcast watcher queue is full"
      description: "Podcast watcher queue is full. New files will be dropped."
  
  # Circuit breaker alert
  - alert: PodcastWatcherCircuitBreakerOpen
    expr: podcast_watcher_cts_consecutive_failures >= 5
    for: 1m
    labels:
      severity: P2
    annotations:
      summary: "Podcast watcher circuit breaker opened"
      description: "Circuit breaker opened after 5 consecutive CTS API failures. Upload attempts paused."
```

### Alertmanager Inhibit Rules for Podcast Watcher

```yaml
inhibit_rules:
  # Suppress upload errors when CTS API is down
  - source_matchers:
      - alertname="PodcastWatcherCTSApiDown"
    target_matchers:
      - alertname="PodcastWatcherUploadErrors"
    equal: ['job']
  
  # Suppress downstream validation alerts when CTS API is down
  - source_matchers:
      - alertname="PodcastWatcherCTSApiDown"
    target_matchers:
      - alertname="PodcastWatcherDownstreamUnhealthyAfterRecovery"
    equal: ['job']
  
  # Suppress queue size alerts when CTS API is down (expected behavior)
  - source_matchers:
      - alertname="PodcastWatcherCTSApiDown"
    target_matchers:
      - alertname="PodcastWatcherQueueSizeHigh"
    equal: ['job']
```

## Grafana Dashboard Template

### Resilient Monitoring Dashboard

```json
{
  "dashboard": {
    "title": "Resilient Service Monitoring",
    "panels": [
      {
        "title": "Service Health",
        "type": "stat",
        "targets": [
          {
            "expr": "service_health_status"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {
              "mode": "thresholds"
            },
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "green", "value": 1}
              ]
            }
          }
        }
      },
      {
        "title": "Dependency Health",
        "type": "stat",
        "targets": [
          {
            "expr": "service_database_health"
          },
          {
            "expr": "service_api_health"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {
              "mode": "thresholds"
            },
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "green", "value": 1}
              ]
            }
          }
        }
      },
      {
        "title": "Queue Size",
        "type": "graph",
        "targets": [
          {
            "expr": "service_queue_size"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 10
            }
          }
        }
      },
      {
        "title": "Retry Attempts",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(service_retry_attempts_total[5m])"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 10
            }
          }
        }
      },
      {
        "title": "Downstream Validation Status",
        "type": "stat",
        "targets": [
          {
            "expr": "service_downstream_validation_status"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {
              "mode": "thresholds"
            },
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "green", "value": 1}
              ]
            }
          }
        }
      },
      {
        "title": "Retry Backoff Seconds",
        "type": "stat",
        "targets": [
          {
            "expr": "service_retry_backoff_seconds"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "s"
          }
        }
      },
      {
        "title": "Consecutive Failures",
        "type": "stat",
        "targets": [
          {
            "expr": "service_consecutive_failures"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {
              "mode": "thresholds"
            },
            "thresholds": {
              "steps": [
                {"color": "green", "value": 0},
                {"color": "yellow", "value": 3},
                {"color": "red", "value": 5}
              ]
            }
          }
        }
      },
      {
        "title": "Error Rate by Type",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(service_errors_total[5m])"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 10
            }
          }
        }
      }
    ]
  }
}
```

## Implementation Checklist

### Application Level
- [ ] Implement dependency health checks
- [ ] Add queuing mechanism for transient failures
- [ ] Implement retry logic with exponential backoff
- [ ] Add circuit breakers for permanent failures
- [ ] Design graceful degradation when dependencies unavailable
- [ ] Expose dependency health metrics
- [ ] Expose queue size metrics
- [ ] Expose retry attempt metrics
- [ ] Implement downstream validation logic
- [ ] Add context-aware error logging

### Monitoring Level
- [ ] Add dependency health metrics to Prometheus
- [ ] Create root cause alerts for dependency failures
- [ ] Implement alert suppression for symptom alerts
- [ ] Add downstream validation alerts
- [ ] Create queue size alerts
- [ ] Build Grafana dashboard with dependency health
- [ ] Add queue monitoring to dashboard
- [ ] Include retry rate visualization
- [ ] Add downstream health status panel

### Documentation Level
- [ ] Document dependency relationships
- [ ] Document graceful recovery mechanisms
- [ ] Document alert suppression logic
- [ ] Create runbook for dependency failures
- [ ] Document downstream validation process
- [ ] Add design feedback loop to incident process

## Design Feedback Loop

### Incident Analysis Template

When downstream failures occur after recovery, use this template:

```markdown
## Downstream Failure After Recovery Analysis

**Service:** [Service Name]
**Dependency:** [Dependency Name]
**Recovery Time:** [Timestamp]
**Downstream Failure:** [Description]

### Graceful Recovery Gap Analysis
- **Current Recovery Mechanism:** [Description]
- **Gap Identified:** [What's missing]
- **Impact:** [How this affects users]

### Improvement Actions
- [ ] Add missing recovery mechanism
- [ ] Improve downstream validation
- [ ] Enhance retry logic
- [ ] Add additional health checks
- [ ] Update documentation

### Design Feedback
- **Pattern to Document:** [New pattern discovered]
- **Template Update Needed:** [Yes/No]
- **Share with Other Services:** [Yes/No]
```

## Usage Examples

### Database-Dependent Service

```python
class DatabaseService(ResilientService):
    def __init__(self):
        super().__init__('database_service', ['database', 'cache'])
        self.queue = deque(maxlen=100)
        self.max_queue_size = 100
        
    def check_database_health(self):
        try:
            # Database health check
            conn = self.get_db_connection()
            conn.execute("SELECT 1")
            return True
        except:
            return False
    
    def check_cache_health(self):
        try:
            # Cache health check
            self.cache_client.ping()
            return True
        except:
            return False
    
    def process_request(self, request):
        return self.process_with_graceful_recovery(
            self.execute_request, 
            request, 
            'database'
        )
```

### API-Dependent Service

```python
class APIService(ResilientService):
    def __init__(self):
        super().__init__('api_service', ['external_api', 'message_queue'])
        self.queue = deque(maxlen=50)
        self.max_queue_size = 50
        
    def check_external_api_health(self):
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def check_message_queue_health(self):
        try:
            self.queue_client.ping()
            return True
        except:
            return False
```

## Continuous Improvement

### Metrics to Track
- Dependency failure frequency
- Queue overflow rate
- Retry success rate
- Downstream validation failure rate
- Mean time to recovery
- Alert suppression effectiveness

### Design Patterns to Document
- Common dependency failure modes
- Effective recovery mechanisms
- Successful retry strategies
- Downstream validation approaches
- Alert suppression patterns

### Knowledge Sharing
- Share recovery patterns across services
- Document common failure scenarios
- Create reusable health check functions
- Build library of resilient monitoring patterns
- Maintain design feedback repository