"""On-demand prices in ₹/hour, ap-south-1. Placeholder for the normalised pricing store (SRS §14.3)."""

HOURLY_INR = {
    't2.micro': 0.97,
    't3.micro': 0.94,
    't3.small': 1.88,
    't3.medium': 3.76,
    't3.large': 7.52,
    'm5.large': 8.10,
    'g4dn.xlarge': 101.14,
    'g5.xlarge': 66.05,
    'p3.2xlarge': 257.0,
    'db.t3.micro': 1.72,
    'db.t3.medium': 6.00,
    'nat-gateway': 3.90,
}

EBS_GP3_INR_PER_GB_HOUR = 7.0 / 730  # ₹7 per GB-month


def hourly_cost(resource_type: str, resource: dict) -> float | None:
    """Running cost per hour, or None when Ward has no price for it. Stopped instances cost nothing for compute."""
    if resource_type == 'aws.ec2':
        if resource.get('State', {}).get('Name') != 'running':
            return 0.0
        return HOURLY_INR.get(resource.get('InstanceType'))
    if resource_type == 'aws.rds':
        return HOURLY_INR.get(resource.get('DBInstanceClass')) if resource.get('DBInstanceStatus') == 'available' else 0.0
    if resource_type == 'aws.ebs':
        return round(resource.get('Size', 0) * EBS_GP3_INR_PER_GB_HOUR, 4)
    if resource_type == 'aws.nat-gateway':
        return HOURLY_INR['nat-gateway']
    if resource_type == 'aws.security-group':
        return 0.0
    return None
