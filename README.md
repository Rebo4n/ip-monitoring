# IP Monitoring Module

Monitors VPC IP allocation and exports metrics to CloudWatch. **CloudWatch alarms handle all notifications** - the Lambda function only collects metrics.

## Architecture

- **Lambda Function**: Collects IP metrics and sends to CloudWatch (no alerting logic)
- **CloudWatch Metrics**: Stores monitoring data for analysis and external tool integration
- **CloudWatch Alarms**: Handle all threshold-based notifications to SNS topics
- **SNS Topic**: Delivers notifications (email, Slack, etc.)

## Features

- **Always Created**: Lambda function, CloudWatch metrics, scheduled execution
- **Optional**: CloudWatch alarms and SNS notifications (controlled by `enable_cloudwatch_alarms`)
- Real-time VPC IP monitoring (total, used, available IPs)
- ENI count tracking  
- External monitoring tool compatible (Prometheus, Grafana, etc.)
- Clean separation: Lambda collects metrics, CloudWatch alarms handle notifications

## Usage

### Basic Usage (with CloudWatch alarms)
```hcl
module "ip_monitoring" {
  source = "git::ssh://git@origin.www.code.dtf.lighting.com:7999/gso_ext/tf-module-ip-monitoring.git?ref=v1.0.2"
  
  name        = "my-vpc"
  vpc_id      = module.vpc.vpc_id
  alert_email = "ops-team@company.com"
}
```

### Metrics Only (no CloudWatch alarms)
```hcl
module "ip_monitoring" {
  source = "git::ssh://git@origin.www.code.dtf.lighting.com:7999/gso_ext/tf-module-ip-monitoring.git?ref=v1.0.2"
  
  name                     = "my-vpc"
  vpc_id                   = module.vpc.vpc_id
  enable_cloudwatch_alarms = false  # Only Lambda + metrics, no alarms
}
```

### With Existing SNS Topic
```hcl
module "ip_monitoring" {
  source = "git::ssh://git@origin.www.code.dtf.lighting.com:7999/gso_ext/tf-module-ip-monitoring.git?ref=v1.0.2"
  
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

CloudWatch alarms monitor the metrics and send notifications via SNS when thresholds are exceeded:

- **Available IPs Low**: Available IPs < 50 (2 evaluation periods)
- **IP Utilization Warning**: IP utilization > 80% (2 evaluation periods) 
- **IP Utilization Critical**: IP utilization > 90% (1 evaluation period)

**Note**: 
- Alerts are handled by **CloudWatch alarms**, not the Lambda function
- Alerts only work when `enable_cloudwatch_alarms = true` (default)
- Lambda function focuses solely on metrics collection

## Usage Modes

### 1. **Full Monitoring** (default)
- ✅ Lambda function collecting metrics
- ✅ CloudWatch metrics
- ✅ CloudWatch alarms (handle notifications)
- ✅ SNS notifications (triggered by alarms)

### 2. **Metrics Only**
- ✅ Lambda function collecting metrics  
- ✅ CloudWatch metrics
- ❌ No CloudWatch alarms
- ❌ No SNS notifications

Use "Metrics Only" mode when you want to collect the data but handle alerting through external tools (Prometheus, Grafana, etc.)

**Key Design**: Lambda function never sends notifications directly - all alerting is handled by CloudWatch alarms for better separation of concerns.

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
