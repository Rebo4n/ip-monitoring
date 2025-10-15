import json
import boto3
import os
from datetime import datetime

def handler(event, context):
    """
    Lambda function to monitor IP allocation in VPC
    """
    ec2 = boto3.client('ec2')
    cloudwatch = boto3.client('cloudwatch')
    sns = boto3.client('sns')
    
    vpc_id = os.environ['VPC_ID']
    sns_topic_arn = os.environ['SNS_TOPIC_ARN']
    warning_threshold = float(os.environ.get('WARNING_THRESHOLD', '80'))
    critical_threshold = float(os.environ.get('CRITICAL_THRESHOLD', '90'))
    
    try:
        # Get VPC information
        vpc_response = ec2.describe_vpcs(VpcIds=[vpc_id])
        vpc_cidr = vpc_response['Vpcs'][0]['CidrBlock']
        
        # Calculate total IPs in VPC (excluding AWS reserved IPs)
        import ipaddress
        network = ipaddress.IPv4Network(vpc_cidr)
        total_ips = network.num_addresses - 5  # AWS reserves 5 IPs per subnet
        
        # Get subnets in VPC
        subnets_response = ec2.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        used_ips = 0
        subnet_details = []
        
        for subnet in subnets_response['Subnets']:
            subnet_id = subnet['SubnetId']
            subnet_cidr = subnet['CidrBlock']
            available_ips = subnet['AvailableIpAddressCount']
            
            # Calculate subnet size
            subnet_network = ipaddress.IPv4Network(subnet_cidr)
            subnet_total = subnet_network.num_addresses - 5
            subnet_used = subnet_total - available_ips
            
            used_ips += subnet_used
            
            subnet_details.append({
                'SubnetId': subnet_id,
                'CIDR': subnet_cidr,
                'TotalIPs': subnet_total,
                'UsedIPs': subnet_used,
                'AvailableIPs': available_ips,
                'UtilizationPercent': (subnet_used / subnet_total) * 100 if subnet_total > 0 else 0
            })
        
        available_ips = total_ips - used_ips
        utilization_percent = (used_ips / total_ips) * 100 if total_ips > 0 else 0
        
        # Get ENI information for detailed IP usage tracking
        enis_response = ec2.describe_network_interfaces(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        eni_count = len(enis_response['NetworkInterfaces'])
        
        # Send metrics to CloudWatch (IP-focused only)
        metrics = [
            {
                'MetricName': 'TotalIPs',
                'Value': total_ips,
                'Unit': 'Count',
                'Dimensions': [{'Name': 'VpcId', 'Value': vpc_id}]
            },
            {
                'MetricName': 'UsedIPs',
                'Value': used_ips,
                'Unit': 'Count',
                'Dimensions': [{'Name': 'VpcId', 'Value': vpc_id}]
            },
            {
                'MetricName': 'AvailableIPs',
                'Value': available_ips,
                'Unit': 'Count',
                'Dimensions': [{'Name': 'VpcId', 'Value': vpc_id}]
            },
            {
                'MetricName': 'IPUtilizationPercent',
                'Value': utilization_percent,
                'Unit': 'Percent',
                'Dimensions': [{'Name': 'VpcId', 'Value': vpc_id}]
            },
            {
                'MetricName': 'ENICount',
                'Value': eni_count,
                'Unit': 'Count',
                'Dimensions': [{'Name': 'VpcId', 'Value': vpc_id}]
            }
        ]
        
        # Send metrics to CloudWatch
        cloudwatch.put_metric_data(
            Namespace='Custom/IPMonitoring',
            MetricData=metrics
        )
        
        # Prepare detailed report
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'vpc_id': vpc_id,
            'vpc_cidr': vpc_cidr,
            'total_ips': total_ips,
            'used_ips': used_ips,
            'available_ips': available_ips,
            'utilization_percent': round(utilization_percent, 2),
            'eni_count': eni_count,
            'subnet_details': subnet_details
        }
        
        # Check for alerts
        alerts = []
        
        if utilization_percent > critical_threshold:
            alerts.append(f"CRITICAL: IP utilization is {utilization_percent:.1f}% (>{critical_threshold}%)")
        elif utilization_percent > warning_threshold:
            alerts.append(f"WARNING: IP utilization is {utilization_percent:.1f}% (>{warning_threshold}%)")
        
        if available_ips < 50:
            alerts.append(f"WARNING: Only {available_ips} IP addresses available")
        
        if available_ips < 20:
            alerts.append(f"CRITICAL: Only {available_ips} IP addresses available")
        
        # Send alerts if necessary
        if alerts:
            alert_message = f"""
IP Allocation Alert for VPC {vpc_id}

Alerts:
{chr(10).join(['- ' + alert for alert in alerts])}

Current Status:
- VPC CIDR: {vpc_cidr}
- Total IPs: {total_ips}
- Used IPs: {used_ips}
- Available IPs: {available_ips}
- Utilization: {utilization_percent:.1f}%
- ENI Count: {eni_count}

Subnet Details:
{chr(10).join([f"- {s['SubnetId']} ({s['CIDR']}): {s['UsedIPs']}/{s['TotalIPs']} IPs used ({s['UtilizationPercent']:.1f}%)" for s in subnet_details])}

Time: {datetime.utcnow().isoformat()}
            """
            
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f"IP Allocation Alert - VPC {vpc_id}",
                Message=alert_message
            )
        
        print(f"IP monitoring completed successfully: {json.dumps(report, indent=2)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps(report)
        }
        
    except Exception as e:
        error_message = f"Error in IP monitoring: {str(e)}"
        print(error_message)
        
        # Send error notification
        try:
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f"IP Monitoring Error - VPC {vpc_id}",
                Message=f"Error occurred during IP monitoring:\n\n{error_message}\n\nTime: {datetime.utcnow().isoformat()}"
            )
        except:
            pass
        
        return {
            'statusCode': 500,
            'body': json.dumps({'error': error_message})
        }
