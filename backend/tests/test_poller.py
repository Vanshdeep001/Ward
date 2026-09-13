from datetime import datetime, timezone

import boto3
from botocore.stub import Stubber

from app.watcher.poller import poll

T = datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_poll_collects_every_resource_type_with_read_only_calls():
    session = boto3.Session(aws_access_key_id='x', aws_secret_access_key='x', region_name='ap-south-1')
    ec2, rds = session.client('ec2'), session.client('rds')

    with Stubber(ec2) as ec2_stub, Stubber(rds) as rds_stub:
        ec2_stub.add_response('describe_instances', {'Reservations': [{'Instances': [
            {'InstanceId': 'i-live', 'InstanceType': 't3.micro', 'LaunchTime': T, 'State': {'Code': 16, 'Name': 'running'}},
            {'InstanceId': 'i-gone', 'InstanceType': 't3.micro', 'LaunchTime': T, 'State': {'Code': 48, 'Name': 'terminated'}},
        ]}]})
        ec2_stub.add_response('describe_volumes', {'Volumes': [{'VolumeId': 'vol-1', 'Size': 20, 'Attachments': []}]})
        ec2_stub.add_response('describe_security_groups', {'SecurityGroups': [{'GroupId': 'sg-1', 'GroupName': 'default', 'OwnerId': '1'}]})
        ec2_stub.add_response('describe_nat_gateways', {'NatGateways': [
            {'NatGatewayId': 'nat-1', 'State': 'available'}, {'NatGatewayId': 'nat-old', 'State': 'deleted'},
        ]})
        rds_stub.add_response('describe_db_instances', {'DBInstances': [
            {'DBInstanceIdentifier': 'db-1', 'PubliclyAccessible': True, 'TagList': [{'Key': 'Owner', 'Value': 'team'}]},
        ]})

        snap = poll(lambda service: {'ec2': ec2, 'rds': rds}[service])

        ec2_stub.assert_no_pending_responses()
        rds_stub.assert_no_pending_responses()

    assert [i['InstanceId'] for i in snap.of_type('aws.ec2')] == ['i-live']
    assert [n['NatGatewayId'] for n in snap.of_type('aws.nat-gateway')] == ['nat-1']
    [db] = snap.of_type('aws.rds')
    assert db['Tags'] == [{'Key': 'Owner', 'Value': 'team'}] and 'TagList' not in db
    assert len(snap.of_type('aws.ebs')) == 1 and len(snap.of_type('aws.security-group')) == 1
