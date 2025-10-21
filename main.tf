# Local value to determine which SNS topic ARN to use
locals {
  sns_topic_arn = var.sns_topic_arn != null ? var.sns_topic_arn : (var.enabled ? aws_sns_topic.ip_alerts[0].arn : null)
}

# IP Monitoring Module
# Monitors VPC IP allocation and sends alerts when thresholds are exceeded

# SNS Topic for IP allocation alerts (create only if sns_topic_arn not provided)
resource "aws_sns_topic" "ip_alerts" {
  count = var.enabled && var.sns_topic_arn == null ? 1 : 0
  name  = "${var.name}-ip-allocation-alerts"


  tags = {
    Name = "${var.name}-ip-alerts"
  }
}

# Email subscription for alerts (optional, only for created topic)
resource "aws_sns_topic_subscription" "ip_alerts_email" {
  count     = var.enabled && var.sns_topic_arn == null && var.alert_email != null ? 1 : 0
  topic_arn = aws_sns_topic.ip_alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Lambda function for detailed IP monitoring
resource "aws_lambda_function" "ip_monitor" {
  count         = var.enabled ? 1 : 0
  filename      = data.archive_file.ip_monitor_zip[0].output_path
  function_name = "${var.name}-ip-monitor"
  role          = aws_iam_role.lambda_ip_monitor[0].arn
  handler       = "index.handler"
  runtime       = "python3.9"
  timeout       = 60

  source_code_hash = data.archive_file.ip_monitor_zip[0].output_base64sha256

  environment {
    variables = {
      VPC_ID = var.vpc_id
    }
  }

  tags = {
    Name        = "${var.name}-ip-monitor"
  }
}

# Create the Lambda deployment package
data "archive_file" "ip_monitor_zip" {
  count       = var.enabled ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/ip_monitor.zip"
  source {
    content  = file("${path.module}/lambda/ip_monitor.py")
    filename = "index.py"
  }
}

# IAM role for Lambda function
resource "aws_iam_role" "lambda_ip_monitor" {
  count = var.enabled ? 1 : 0
  name  = "${var.name}-lambda-ip-monitor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.name}-lambda-ip-monitor-role"
  }
}

# IAM policy for Lambda function
resource "aws_iam_role_policy" "lambda_ip_monitor_policy" {
  count = var.enabled ? 1 : 0
  name  = "${var.name}-lambda-ip-monitor-policy"
  role  = aws_iam_role.lambda_ip_monitor[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeRouteTables",
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      }
    ])
  })
}

# CloudWatch Event Rule to trigger Lambda
resource "aws_cloudwatch_event_rule" "ip_monitor_schedule" {
  count               = var.enabled ? 1 : 0
  name                = "${var.name}-ip-monitor-schedule"
  description         = "Trigger IP monitoring Lambda"
  schedule_expression = var.monitoring_frequency

  tags = {
    Name        = "${var.name}-ip-monitor-schedule"
  }
}

# CloudWatch Event Target
resource "aws_cloudwatch_event_target" "ip_monitor_target" {
  count     = var.enabled ? 1 : 0
  rule      = aws_cloudwatch_event_rule.ip_monitor_schedule[0].name
  target_id = "TriggerLambdaFunction"
  arn       = aws_lambda_function.ip_monitor[0].arn
}

# Lambda permission for CloudWatch Events
resource "aws_lambda_permission" "allow_cloudwatch" {
  count         = var.enabled ? 1 : 0
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ip_monitor[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ip_monitor_schedule[0].arn
}

# CloudWatch Log Group for Lambda logs
resource "aws_cloudwatch_log_group" "ip_monitor_logs" {
  count             = var.enabled ? 1 : 0
  name              = "/aws/lambda/${aws_lambda_function.ip_monitor[0].function_name}"
  retention_in_days = 14

  tags = {
    Name        = "${var.name}-ip-monitor-logs"
  }
}

# CloudWatch Alarms for IP monitoring
resource "aws_cloudwatch_metric_alarm" "available_ips_low" {
  count               = var.enabled && var.enable_cloudwatch_alarms ? 1 : 0
  alarm_name          = "${var.name}-available-ips-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "AvailableIPs"
  namespace           = "Custom/IPMonitoring"
  period              = "300"
  statistic           = "Average"
  threshold           = "50"
  alarm_description   = "Available IP addresses are running low"
  alarm_actions       = [local.sns_topic_arn]

  dimensions = {
    VpcId = var.vpc_id
  }

  tags = {
    Name        = "${var.name}-available-ips-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "ip_utilization_warning" {
  count               = var.enabled && var.enable_cloudwatch_alarms ? 1 : 0
  alarm_name          = "${var.name}-ip-utilization-warning"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "IPUtilizationPercent"
  namespace           = "Custom/IPMonitoring"
  period              = "300"
  statistic           = "Average"
  threshold           = var.warning_threshold
  alarm_description   = "IP utilization is high (>${var.warning_threshold}%)"
  alarm_actions       = [local.sns_topic_arn]

  dimensions = {
    VpcId = var.vpc_id
  }

  tags = {
    Name        = "${var.name}-ip-utilization-warning"
  }
}

resource "aws_cloudwatch_metric_alarm" "ip_utilization_critical" {
  count               = var.enabled && var.enable_cloudwatch_alarms ? 1 : 0
  alarm_name          = "${var.name}-ip-utilization-critical"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "IPUtilizationPercent"
  namespace           = "Custom/IPMonitoring"
  period              = "300"
  statistic           = "Average"
  threshold           = var.critical_threshold
  alarm_description   = "IP utilization is critically high (>${var.critical_threshold}%)"
  alarm_actions       = [local.sns_topic_arn]

  dimensions = {
    VpcId = var.vpc_id
  }

  tags = {
    Name        = "${var.name}-ip-utilization-critical"
  }
}
