import json
import boto3
import os
from datetime import datetime

def handler(event, context):
    """
    Lambda function to monitor IP allocation in VPC and send metrics to CloudWatch
    Alerts are handled by CloudWatch alarms, not this Lambda
    """
    ec2 = boto3.client('ec2')
    cloudwatch = boto3.client('cloudwatch')
    
    vpc_id = os.environ['VPC_ID']
    
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
        
        # Send metrics to CloudWatch (per-subnet and VPC-level)
        metrics = []
        
        # Per-subnet metrics with SubnetId and VpcId dimensions
        for subnet_detail in subnet_details:
            subnet_id = subnet_detail['SubnetId']
            
            # Determine subnet type (private/public) based on route table
            subnet_type = "private"  # default assumption
            try:
                # Check if subnet has route to internet gateway (indicates public subnet)
                route_tables = ec2.describe_route_tables(
                    Filters=[
                        {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                    ]
                )
                
                for rt in route_tables['RouteTables']:
                    for route in rt['Routes']:
                        if route.get('DestinationCidrBlock') == '0.0.0.0/0' and 'GatewayId' in route and route['GatewayId'].startswith('igw-'):
                            subnet_type = "public"
                            break
                    if subnet_type == "public":
                        break
            except Exception:
                # If we can't determine, assume private
                pass
            
            # Add per-subnet metrics
            subnet_metrics = [
                {
                    'MetricName': 'SubnetTotalIPs',
                    'Value': subnet_detail['TotalIPs'],
                    'Unit': 'Count',
                    'Dimensions': [
                        {'Name': 'VpcId', 'Value': vpc_id},
                        {'Name': 'SubnetId', 'Value': subnet_id},
                        {'Name': 'SubnetType', 'Value': subnet_type}
                    ]
                },
                {
                    'MetricName': 'SubnetUsedIPs',
                    'Value': subnet_detail['UsedIPs'],
                    'Unit': 'Count',
                    'Dimensions': [
                        {'Name': 'VpcId', 'Value': vpc_id},
                        {'Name': 'SubnetId', 'Value': subnet_id},
                        {'Name': 'SubnetType', 'Value': subnet_type}
                    ]
                },
                {
                    'MetricName': 'SubnetAvailableIPs',
                    'Value': subnet_detail['AvailableIPs'],
                    'Unit': 'Count',
                    'Dimensions': [
                        {'Name': 'VpcId', 'Value': vpc_id},
                        {'Name': 'SubnetId', 'Value': subnet_id},
                        {'Name': 'SubnetType', 'Value': subnet_type}
                    ]
                },
                {
                    'MetricName': 'SubnetIPUtilizationPercent',
                    'Value': subnet_detail['UtilizationPercent'],
                    'Unit': 'Percent',
                    'Dimensions': [
                        {'Name': 'VpcId', 'Value': vpc_id},
                        {'Name': 'SubnetId', 'Value': subnet_id},
                        {'Name': 'SubnetType', 'Value': subnet_type}
                    ]
                }
            ]
            metrics.extend(subnet_metrics)
            
            # Update subnet_detail with type for logging
            subnet_detail['SubnetType'] = subnet_type
        
        # VPC-level aggregate metrics (keep existing for backward compatibility)
        vpc_metrics = [
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
        metrics.extend(vpc_metrics)
        
        # Send metrics to CloudWatch
        cloudwatch.put_metric_data(
            Namespace='Custom/IPMonitoring',
            MetricData=metrics
        )
        
        # Prepare detailed report for logging
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
        
        print(f"IP monitoring completed successfully: {json.dumps(report, indent=2)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps(report)
        }
        
    except Exception as e:
        error_message = f"Error in IP monitoring: {str(e)}"
        print(error_message)
        
        return {
            'statusCode': 500,
            'body': json.dumps({'error': error_message})
        }
