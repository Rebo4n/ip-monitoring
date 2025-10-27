variable "name" {
  description = "Base name for resources"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID to monitor"
  type        = string
}

variable "enabled" {
  description = "Enable IP monitoring module"
  type        = bool
  default     = true
}


variable "enable_cloudwatch_alarms" {
  description = "Enable CloudWatch alarm rules for IP monitoring"
  type        = bool
  default     = true
}

variable "alert_email" {
  description = "Email address for IP allocation alerts (optional)"
  type        = string
  default     = null
}

variable "sns_topic_arn" {
  description = "Existing SNS topic ARN for alerts (optional - creates new topic if not provided)"
  type        = string
  default     = null
}

variable "warning_threshold" {
  description = "IP utilization percentage threshold for warnings"
  type        = number
  default     = 80
}

variable "critical_threshold" {
  description = "IP utilization percentage threshold for critical alerts"
  type        = number
  default     = 90
}

variable "monitoring_frequency" {
  description = "How often to run IP monitoring (CloudWatch Events schedule expression)"
  type        = string
  default     = "rate(24 hours)"
}
