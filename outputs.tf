output "sns_topic_arn" {
  description = "ARN of the SNS topic for IP alerts (either provided or created)"
  value       = var.enabled ? local.sns_topic_arn : null
}

output "lambda_function_name" {
  description = "Name of the IP monitoring Lambda function"
  value       = var.enabled ? aws_lambda_function.ip_monitor[0].function_name : null
}

output "lambda_function_arn" {
  description = "ARN of the IP monitoring Lambda function"
  value       = var.enabled ? aws_lambda_function.ip_monitor[0].arn : null
}


output "cloudwatch_log_group" {
  description = "CloudWatch log group for IP monitoring"
  value       = var.enabled ? aws_cloudwatch_log_group.ip_monitor_logs[0].name : null
}

output "cloudwatch_alarms_enabled" {
  description = "Whether CloudWatch alarms are enabled"
  value       = var.enabled && var.enable_cloudwatch_alarms
}

output "available_ips_alarm_arn" {
  description = "ARN of the available IPs CloudWatch alarm (if enabled)"
  value       = var.enabled && var.enable_cloudwatch_alarms ? aws_cloudwatch_metric_alarm.available_ips_low[0].arn : null
}

output "ip_utilization_warning_alarm_arn" {
  description = "ARN of the IP utilization warning CloudWatch alarm (if enabled)"
  value       = var.enabled && var.enable_cloudwatch_alarms ? aws_cloudwatch_metric_alarm.ip_utilization_warning[0].arn : null
}

output "ip_utilization_critical_alarm_arn" {
  description = "ARN of the IP utilization critical CloudWatch alarm (if enabled)"
  value       = var.enabled && var.enable_cloudwatch_alarms ? aws_cloudwatch_metric_alarm.ip_utilization_critical[0].arn : null
}
