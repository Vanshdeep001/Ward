from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_inventory
from app.engine.custodian import resource_id
from app.inventory.pricing import hourly_cost
from app.inventory.store import InventoryStore

router = APIRouter(tags=['resources'])

SHORT_TYPES = {'aws.ec2': 'ec2', 'aws.ebs': 'ebs', 'aws.rds': 'rds', 'aws.security-group': 'sg', 'aws.nat-gateway': 'nat'}


@router.get('/resources')
def list_resources(inventory: InventoryStore = Depends(get_inventory)):
    """Latest inventory in the shape the frontend's Resources page reads."""
    snap = inventory.latest()
    now = datetime.now(timezone.utc)
    items = []
    for rtype, resources in snap.resources.items():
        for r in resources:
            tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}
            running = _is_running(rtype, r)
            launched = r.get('LaunchTime') or r.get('CreateTime') or r.get('InstanceCreateTime')
            az = r.get('Placement', {}).get('AvailabilityZone') or r.get('AvailabilityZone') or ''
            items.append({
                'id': resource_id(rtype, r),
                'name': tags.get('Name') or r.get('GroupName') or r.get('DBInstanceIdentifier') or resource_id(rtype, r),
                'type': SHORT_TYPES[rtype],
                'instanceType': r.get('InstanceType') or r.get('DBInstanceClass'),
                'region': az[:-1] if az else None,
                'running': running,
                'attached': bool(r.get('Attachments')) if rtype == 'aws.ebs' else None,
                'launchedAt': launched.isoformat() if launched else None,
                'runtimeHours': round((now - r['LaunchTime']).total_seconds() / 3600) if rtype == 'aws.ec2' and running else 0,
                'costPerHour': hourly_cost(rtype, r) or 0,
                'tags': {k: v for k, v in tags.items() if k != 'Name'},
                # No active guardrails are evaluated server-side yet, so every resource is in its initial state.
                'state': 'discovered',
            })
    return {'asOf': snap.taken_at.isoformat(), 'items': items}


def _is_running(rtype: str, r: dict) -> bool:
    if rtype == 'aws.ec2':
        return r['State']['Name'] == 'running'
    if rtype == 'aws.rds':
        return r.get('DBInstanceStatus') == 'available'
    return rtype == 'aws.nat-gateway' and r.get('State') == 'available'
