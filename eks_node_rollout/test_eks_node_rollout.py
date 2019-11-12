#!/usr/bin/env python3
import sys
print(sys.path)
import pytest
from eks_node_rollout import *
from botocore.stub import Stubber, ANY
import botocore.exceptions

def test_add_node():
    asg_client = boto3.client("autoscaling", region_name="ap-southeast-2")
    stubber = Stubber(asg_client)
    mock_response = {
        'AutoScalingGroups': [
            {
                "AutoScalingGroupName": "foobar",
                "DesiredCapacity": 5,
                # these are useless but required to for mock to run
                "MinSize": 1,
                "MaxSize": 10,
                "DefaultCooldown": 20,
                "AvailabilityZones": ["ap-southeast-2a"],
                "HealthCheckType": "EC2",
                "CreatedTime": datetime.datetime.now() - datetime.timedelta(days=1)
            }
        ]
    }
    stubber.add_response('describe_auto_scaling_groups', mock_response)
    stubber.add_response('set_desired_capacity', {})
    stubber.activate()
    assert add_node(asg_client=asg_client, asg_name="foobar") is None


def test_describe_nodes_not_matching_lt():
    asg_client = boto3.client("autoscaling", region_name="ap-southeast-2")
    asg_stubber = Stubber(asg_client)
    ec2_client = boto3.client("ec2", region_name="ap-southeast-2")
    ec2_stubber = Stubber(ec2_client)
    mock_response = {
        'AutoScalingGroups': [
            {
                "AutoScalingGroupName": "foobar",
                "MinSize": 1,
                "DesiredCapacity": 5,
                "MaxSize": 10,
                "DefaultCooldown": 20,
                "AvailabilityZones": ["ap-southeast-2a"],
                "HealthCheckType": "EC2",
                "CreatedTime": datetime.datetime.now() - datetime.timedelta(days=1),
                "MixedInstancesPolicy": {
                    "LaunchTemplate": {
                        "LaunchTemplateSpecification": {
                            "Version": "$Latest",
                            "LaunchTemplateId": "new"
                        }
                    }
                },
                "Instances": [
                    {
                        "InstanceId": "oldest",
                        "LaunchTemplate": {
                            "Version": "1",
                            "LaunchTemplateId": "old"
                        },
                        # these are useless but required to for mock to run
                        "AvailabilityZone": "ap-southeast-2a",
                        "LifecycleState": "InService",
                        'HealthStatus': 'string',
                        'ProtectedFromScaleIn': False
                    },
                    {
                        "InstanceId": "newer",
                        "LaunchTemplate": {
                            "Version": "1",
                            "LaunchTemplateId": "old"
                        },
                        "AvailabilityZone": "ap-southeast-2a",
                        "LifecycleState": "InService",
                        'HealthStatus': 'string',
                        'ProtectedFromScaleIn': False
                    },
                    {
                        "InstanceId": "newest",
                        "LaunchTemplate": {
                            "Version": "2",
                            "LaunchTemplateId": "new"
                        },
                        "AvailabilityZone": "ap-southeast-2a",
                        "LifecycleState": "InService",
                        'HealthStatus': 'string',
                        'ProtectedFromScaleIn': False
                    }
                ]
            }
        ]
    }
    asg_stubber.add_response('describe_auto_scaling_groups', mock_response)
    mock_response = {
        "Reservations": [
            {
                "Instances": [                                                                                                                                                                                                             
                    {                                                                                                                                                                                                                      
                        'InstanceId': "foo",                                                                                                                                                                                            
                        "PrivateDnsName": "foo.aws.local",
                        "LaunchTime": datetime.datetime.now() - datetime.timedelta(days=1)                                                                                                                                                 
                    },                                                                                             
                    {                                                                                                                                                                                                                      
                        'InstanceId': "bar",                                                                                                                                                                                            
                        "PrivateDnsName": "bar.aws.local",
                        "LaunchTime": datetime.datetime.now() - datetime.timedelta(days=2)                                                                                                                                                 
                    }                                                                                                                                                                                                                      
                ]      
            }
        ]
    }

    ec2_stubber.add_response('describe_instances', mock_response)

    asg_stubber.activate()
    ec2_stubber.activate()

    instances = describe_nodes_not_matching_lt(asg_client=asg_client, ec2_client=ec2_client, asg_name="foobar")
    assert len(instances) == 2
