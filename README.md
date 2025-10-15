# IP Monitoring Module

Monitors VPC IP allocation and sends alerts when thresholds are exceeded. Metrics are exported to CloudWatch for external monitoring tools.

## Features

- **Always Created**: Lambda function, CloudWatch metrics, scheduled execution
- **Optional**: CloudWatch alarms and SNS notifications (controlled by `enable_cloudwatch_alarms`)
- Real-time VPC IP monitoring (total, used, available IPs)
- ENI count tracking  
- External monitoring tool compatible (Prometheus, Grafana, etc.)

## Usage

### Basic Usage (with CloudWatch alarms)
```hcl
module "ip_monitoring" {
  source = "./modules/ip-monitoring"
  
  name        = "my-vpc"
  vpc_id      = module.vpc.vpc_id
}
```

### Metrics Only (no CloudWatch alarms)
```hcl
module "ip_monitoring" {
  source = "./modules/ip-monitoring"
  
  name                     = "my-vpc"
  vpc_id                   = module.vpc.vpc_id
  enable_cloudwatch_alarms = false  # Only Lambda + metrics, no alarms
}
```

### With Existing SNS Topic
```hcl
module "ip_monitoring" {
  source = "./modules/ip-monitoring"
  
  name          = "my-vpc"
  vpc_id        = module.vpc.vpc_id
  sns_topic_arn = "arn:aws:sns:region:account:existing-topic"
}
```

## Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `name` | string | - | Name prefix for resources |
| `vpc_id` | string | - | VPC ID to monitor |
| `enabled` | bool | `true` | Enable/disable module |
| `enable_cloudwatch_alarms` | bool | `true` | Enable CloudWatch alarms |
| `alert_email` | string | `null` | Email for alerts |
| `sns_topic_arn` | string | `null` | Existing SNS topic ARN |
| `warning_threshold` | number | `80.0` | Warning threshold % |
| `critical_threshold` | number | `90.0` | Critical threshold % |
| `monitoring_frequency` | string | `"rate(5 minutes)"` | Schedule expression |

## Metrics

**CloudWatch** (namespace: `Custom/IPMonitoring`):
- `TotalIPs`, `UsedIPs`, `AvailableIPs`, `IPUtilizationPercent`, `ENICount`
- Dimensions: `VpcId`
- Can be scraped by external monitoring tools (Prometheus CloudWatch exporter, etc.)

## Alerts

- **Warning**: IP utilization > 80% OR available IPs < 50
- **Critical**: IP utilization > 90% OR available IPs < 20

**Note**: Alerts only work when `enable_cloudwatch_alarms = true` (default)

## Usage Modes

### 1. **Full Monitoring** (default)
- ✅ Lambda function collecting metrics
- ✅ CloudWatch metrics
- ✅ CloudWatch alarms
- ✅ SNS notifications

### 2. **Metrics Only**
- ✅ Lambda function collecting metrics  
- ✅ CloudWatch metrics
- ❌ No CloudWatch alarms
- ❌ No SNS notifications

Use "Metrics Only" mode when you want to collect the data but handle alerting through external tools (Prometheus, Grafana, etc.)

## External Monitoring Integration

The Lambda sends metrics to CloudWatch which can be scraped by external monitoring tools:

**Prometheus CloudWatch Exporter**:
```yaml
# cloudwatch_exporter config
- aws_namespace: Custom/IPMonitoring
  aws_metric_name: IPUtilizationPercent
  aws_dimensions: [VpcId]
```

## Verification

```bash
# Check Lambda logs
aws logs tail /aws/lambda/my-cluster-ip-monitor --follow

# List CloudWatch metrics
aws cloudwatch list-metrics --namespace "Custom/IPMonitoring"
```

## Outputs

- `lambda_function_arn`: Lambda function ARN
- `sns_topic_arn`: SNS topic ARN for alerts
- `cloudwatch_event_rule_arn`: CloudWatch Events rule ARN
