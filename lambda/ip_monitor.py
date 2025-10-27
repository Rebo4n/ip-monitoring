import json
import boto3
import os
from datetime import datetime
import ipaddress
from itertools import islice

ec2 = boto3.client('ec2')
cloudwatch = boto3.client('cloudwatch')

NAMESPACE = 'Custom/IPMonitoring'

def _chunk(seq, n):
    it = iter(seq)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            return
        yield chunk

def compute_metrics_for_vpc(vpc_id: str):
    # Get subnets in VPC
    subnets = []
    paginator = ec2.get_paginator('describe_subnets')
    for page in paginator.paginate(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]):
        subnets.extend(page['Subnets'])

    used_ips = 0
    subnet_details = []
    total_ips_sum = 0  # we'll sum per-subnet totals (more accurate than VPC CIDR)

    for subnet in subnets:
        subnet_id = subnet['SubnetId']
        subnet_cidr = subnet['CidrBlock']
        available_ips = subnet['AvailableIpAddressCount']

        subnet_network = ipaddress.IPv4Network(subnet_cidr)
        subnet_total = subnet_network.num_addresses - 5  # AWS reserves 5 per subnet
        subnet_used = max(subnet_total - available_ips, 0)

        used_ips += subnet_used
        total_ips_sum += subnet_total

        # Determine subnet type via route to IGW
        subnet_type = "private"
        try:
            rts = ec2.describe_route_tables(
                Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
            )['RouteTables']
            for rt in rts:
                for route in rt.get('Routes', []):
                    if route.get('DestinationCidrBlock') == '0.0.0.0/0' and route.get('GatewayId', '').startswith('igw-'):
                        subnet_type = "public"
                        raise StopIteration
        except StopIteration:
            pass
        except Exception:
            pass

        subnet_details.append({
            'SubnetId': subnet_id,
            'CIDR': subnet_cidr,
            'TotalIPs': subnet_total,
            'UsedIPs': subnet_used,
            'AvailableIPs': available_ips,
            'UtilizationPercent': (subnet_used / subnet_total) * 100 if subnet_total > 0 else 0,
            'SubnetType': subnet_type
        })

    total_ips = total_ips_sum
    available_ips = max(total_ips - used_ips, 0)
    utilization_percent = (used_ips / total_ips) * 100 if total_ips > 0 else 0

    # Count ENIs in this VPC
    eni_count = 0
    eni_paginator = ec2.get_paginator('describe_network_interfaces')
    for page in eni_paginator.paginate(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]):
        eni_count += len(page['NetworkInterfaces'])

    # Build metrics
    metrics = []

    # Per-subnet
    for s in subnet_details:
        dims = [
            {'Name': 'VpcId', 'Value': vpc_id},
            {'Name': 'SubnetId', 'Value': s['SubnetId']},
            {'Name': 'SubnetType', 'Value': s['SubnetType']},
        ]
        metrics.extend([
            {'MetricName': 'SubnetTotalIPs',           'Value': s['TotalIPs'],          'Unit': 'Count',   'Dimensions': dims},
            {'MetricName': 'SubnetUsedIPs',            'Value': s['UsedIPs'],           'Unit': 'Count',   'Dimensions': dims},
            {'MetricName': 'SubnetAvailableIPs',       'Value': s['AvailableIPs'],      'Unit': 'Count',   'Dimensions': dims},
            {'MetricName': 'SubnetIPUtilizationPercent','Value': s['UtilizationPercent'],'Unit': 'Percent', 'Dimensions': dims},
        ])

    # VPC-level
    vpc_dims = [{'Name': 'VpcId', 'Value': vpc_id}]
    metrics.extend([
        {'MetricName': 'TotalIPs',           'Value': total_ips,          'Unit': 'Count',   'Dimensions': vpc_dims},
        {'MetricName': 'UsedIPs',            'Value': used_ips,           'Unit': 'Count',   'Dimensions': vpc_dims},
        {'MetricName': 'AvailableIPs',       'Value': available_ips,      'Unit': 'Count',   'Dimensions': vpc_dims},
        {'MetricName': 'IPUtilizationPercent','Value': utilization_percent,'Unit': 'Percent', 'Dimensions': vpc_dims},
        {'MetricName': 'ENICount',           'Value': eni_count,          'Unit': 'Count',   'Dimensions': vpc_dims},
    ])

    # Put in chunks of 20
    for batch in _chunk(metrics, 20):
        cloudwatch.put_metric_data(Namespace=NAMESPACE, MetricData=batch)

    report = {
        'timestamp': datetime.utcnow().isoformat(),
        'vpc_id': vpc_id,
        'total_ips': total_ips,
        'used_ips': used_ips,
        'available_ips': available_ips,
        'utilization_percent': round(utilization_percent, 2),
        'eni_count': eni_count,
        'subnet_details': subnet_details
    }
    return report

def compute_metrics_for_all_vpcs():
    vpcs = []
    paginator = ec2.get_paginator('describe_vpcs')
    for page in paginator.paginate():
        vpcs.extend([v['VpcId'] for v in page['Vpcs']])

    results = []
    for vpc_id in vpcs:
        try:
            results.append(compute_metrics_for_vpc(vpc_id))
        except Exception as e:
            print(f"Error computing metrics for {vpc_id}: {e}")
    return results

def _extract_eni_id_from_event(event: dict):
    d = event.get('detail', {}) or {}
    # requestParameters.networkInterfaceId (Delete/Attach/Detach)
    eni_id = (d.get('requestParameters', {}) or {}).get('networkInterfaceId')
    if eni_id:
        return eni_id
    # responseElements.networkInterface.networkInterfaceId (Create)
    eni_id = ((d.get('responseElements', {}) or {}).get('networkInterface', {}) or {}).get('networkInterfaceId')
    return eni_id

def handler(event, context):
    try:
        is_cloudtrail = (
            isinstance(event, dict)
            and event.get('source') == 'aws.ec2'
            and event.get('detail-type') == 'AWS API Call via CloudTrail'
        )

        if is_cloudtrail:
            eni_id = _extract_eni_id_from_event(event)
            if eni_id:
                eni = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])['NetworkInterfaces'][0]
                vpc_id = eni['VpcId']
                subnet_id = eni['SubnetId']
                print(f"Triggered by ENI event {event.get('detail',{}).get('eventName')} | ENI: {eni_id} | VPC: {vpc_id} | Subnet: {subnet_id}")
                report = compute_metrics_for_vpc(vpc_id)
                return {'statusCode': 200, 'body': json.dumps({'mode': 'eni_event', 'eni_id': eni_id, 'report': report})}
            else:
                print("CloudTrail event but no ENI ID found; running full scan.")
                results = compute_metrics_for_all_vpcs()
                return {'statusCode': 200, 'body': json.dumps({'mode': 'full_scan_fallback', 'results': results})}

        # Normal/manual/scheduled invocation
        default_vpc = os.getenv('VPC_ID', '').strip()
        if default_vpc:
            print(f"Normal invocation; scanning default VPC {default_vpc}")
            report = compute_metrics_for_vpc(default_vpc)
            return {'statusCode': 200, 'body': json.dumps({'mode': 'default_vpc', 'report': report})}
        else:
            print("Normal invocation; scanning all VPCs")
            results = compute_metrics_for_all_vpcs()
            return {'statusCode': 200, 'body': json.dumps({'mode': 'all_vpcs', 'results': results})}

    except Exception as e:
        msg = f"Error in IP monitoring: {e}"
        print(msg)
        return {'statusCode': 500, 'body': json.dumps({'error': msg})}
