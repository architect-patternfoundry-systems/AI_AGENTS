# GitOps Implementation Checklist

## NetworkPolicy Changes

### Files to Add/Update

- [ ] **infrastructure/** (or appropriate repository path)
  - [ ] `networkpolicies/toneroot/allow-prometheus-scrape.yaml`
    - Updated with egress rules for flux-system, infra-data, kube-system
    - Added DNS access to all namespaces
    - Maintains existing node-exporter access
  - [ ] `networkpolicies/infra-data/allow-prometheus-scrape.yaml`
    - New file for CNPG metrics ingress
    - Targets pods with `cnpg.io/cluster` label
  - [ ] `networkpolicies/kube-system/allow-prometheus-scrape.yaml`
    - New file for CoreDNS metrics ingress
    - Targets pods with `k8s-app: kube-dns` label
  - [ ] `networkpolicies/toneroot/allow-redis-exporter-to-redis.yaml`
    - New file for Redis exporter connectivity
    - Targets redis-exporter pods to Redis service

### Validation Steps

- [x] Apply NetworkPolicy changes in development environment first
- [x] Verify Prometheus targets show improved scrape success
- [x] Test cross-namespace connectivity from Prometheus pod
- [x] Confirm no unintended side effects on other workloads (Resolved critical port 53 ingress block regression on 2026-07-22)
- [x] Monitor for 24-48 hours before production deployment

## ServiceMonitor Addition

### Files to Add

- [ ] **toneroot/** (or appropriate repository path)
  - [ ] `servicemonitors/kube-prometheus-stack-prometheus-node-exporter.yaml`
    - ServiceMonitor for node-exporter
    - Targets node-exporter pods on port 9100
    - Uses `node-exporter` job label

### Validation Steps

- [ ] Apply ServiceMonitor in development environment
- [ ] Verify node-exporter targets appear in Prometheus
- [ ] Confirm node-level metrics are being collected
- [ ] Check that all 3 nodes are being scraped
- [ ] Validate dashboard data population

## Dashboard Configuration

### Dashboards to Add

- [ ] **Grafana Dashboard 16450:** "Kubernetes Views K3s Cluster"
  - [ ] Import dashboard JSON
  - [ ] Configure Prometheus datasource
  - [ ] Add to appropriate folder
  - [ ] Test panel data population

- [ ] **Node Exporter Dashboards:**
  - [ ] Node Exporter Full (ID: 1860)
  - [ ] Node Exporter for Prometheus (ID: 11074)
  - [ ] Configure for K3s environment

- [ ] **Flux Dashboards:**
  - [ ] Flux GitOps Dashboard
  - [ ] Configure for Flux controller metrics

- [ ] **PostgreSQL/CNPG Dashboards:**
  - [ ] PostgreSQL Database (ID: 9628)
  - [ ] CNPG-specific dashboards if available

### Dashboards to Disable/Hide

- [ ] **Control-plane dashboards:**
  - [ ] Kubernetes / Scheduler
  - [ ] Kubernetes / Controller Manager
  - [ ] Kubernetes / Etcd
  - [ ] Mark as hidden or move to archive folder

- [ ] **Kubelet-specific dashboards:**
  - [ ] Kubelet-heavy panels
  - [ ] cAdvisor container dashboards
  - [ ] Document as incompatible with K3s

### Dashboard Organization

- [ ] Create folder structure:
  - [ ] "K3s Cluster" - K3s-specific dashboards
  - [ ] "Workloads" - Application and service dashboards
  - [ ] "Infrastructure" - Node and system metrics
  - [ ] "GitOps" - Flux and deployment dashboards
  - [ ] "Archive" - Incompatible standard Kubernetes dashboards

## Documentation Updates

### Operational Documentation

- [ ] **Monitoring Runbook:**
  - [ ] Document K3s-specific monitoring approach
  - [ ] Explain available vs unavailable metrics
  - [ ] Include dashboard selection guidelines
  - [ ] Add troubleshooting procedures

- [ ] **NetworkPolicy Documentation:**
  - [ ] Document Prometheus scrape path requirements
  - [ ] Explain policy rationale and scope
  - [ ] Include change approval process
  - [ ] Add rollback procedures

- [ ] **Architecture Documentation:**
  - [ ] Update system architecture diagrams
  - [ ] Document K3s monitoring limitations
  - [ ] Include alternative metrics sources
  - [ ] Add decision records for dashboard choices

## GitOps Repository Structure

### Suggested Structure

```
infrastructure/
├── networkpolicies/
│   ├── toneroot/
│   │   ├── allow-prometheus-scrape.yaml
│   │   └── allow-redis-exporter-to-redis.yaml
│   ├── infra-data/
│   │   └── allow-prometheus-scrape.yaml
│   └── kube-system/
│       └── allow-prometheus-scrape.yaml
├── servicemonitors/
│   └── toneroot/
│       └── kube-prometheus-stack-prometheus-node-exporter.yaml
└── dashboards/
    ├── k3s-cluster/
    │   └── k3s-cluster-overview.json
    ├── infrastructure/
    │   ├── node-exporter-full.json
    │   └── node-exporter-prometheus.json
    └── gitops/
        └── flux-gitops.json
```

## Testing and Validation

### Pre-deployment Testing

- [ ] **NetworkPolicy Testing:**
  - [ ] Test in development/staging environment
  - [ ] Verify Prometheus scrape success rates
  - [ ] Confirm no workload connectivity issues
  - [ ] Test rollback procedures

- [ ] **ServiceMonitor Testing:**
  - [ ] Verify node-exporter target discovery
  - [ ] Confirm metrics collection
  - [ ] Test dashboard data population
  - [ ] Validate alert rules if applicable

- [ ] **Dashboard Testing:**
  - [ ] Test all new dashboards load correctly
  - [ ] Verify data sources are connected
  - [ ] Check panel queries return data
  - [ ] Validate time range selections

### Post-deployment Validation

- [ ] **Immediate Checks (1 hour):**
  - [ ] Verify Prometheus target health
  - [ ] Check dashboard accessibility
  - [ ] Confirm no error logs in Prometheus/Grafana
  - [ ] Validate NetworkPolicy effectiveness

- [ ] **Short-term Monitoring (24-48 hours):**
  - [ ] Monitor scrape success rates
  - [ ] Check for any connectivity issues
  - [ ] Review dashboard performance
  - [ ] Validate alert functionality

- [ ] **Long-term Monitoring (1-2 weeks):**
  - [ ] Review monitoring stability
  - [ ] Assess dashboard usefulness
  - [ ] Identify any additional tuning needs
  - [ ] Document any lessons learned

## Rollback Procedures

### NetworkPolicy Rollback

- [ ] Document previous NetworkPolicy configurations
- [ ] Test rollback in development environment
- [ ] Create rollback script or procedure
- [ ] Identify impact scope of rollback
- [ ] Define rollback triggers

### ServiceMonitor Rollback

- [ ] Remove ServiceMonitor if issues arise
- [ ] Verify node-exporter continues functioning
- [ ] Test alternative monitoring if needed
- [ ] Document rollback impact

## Ongoing Maintenance

### Regular Tasks

- [ ] **Weekly:**
  - [ ] Review Prometheus target health
  - [ ] Check dashboard performance
  - [ ] Monitor for NetworkPolicy issues

- [ ] **Monthly:**
  - [ ] Review dashboard effectiveness
  - [ ] Update documentation as needed
  - [ ] Assess need for additional dashboards
  - [ ] Review alert rules and thresholds

- [ ] **Quarterly:**
  - [ ] Comprehensive monitoring review
  - [ ] Update K3s compatibility assessment
  - [ ] Review and update NetworkPolicies
  - [ ] Dashboard library cleanup and optimization

## Success Criteria

- [ ] All NetworkPolicy changes successfully deployed via GitOps
- [ ] ServiceMonitor for node-exporter operational
- [ ] K3s-appropriate dashboards deployed and functional
- [ ] Incompatible dashboards documented and archived
- [ ] Monitoring success rate maintained at >70%
- [ ] Documentation updated and complete
- [ ] Rollback procedures tested and documented
- [ ] Team trained on new monitoring approach

## Notes and Considerations

- **Redis Exporter:** Still experiencing timeout issues - separate investigation needed
- **Kubelet Metrics:** Accepted as K3s architectural limitation
- **Future K3s Updates:** Monitor for changes in K3s metrics exposure
- **Dashboard Evolution:** Regular review and update cycle recommended
- **Security:** Maintain least privilege principle for NetworkPolicies
