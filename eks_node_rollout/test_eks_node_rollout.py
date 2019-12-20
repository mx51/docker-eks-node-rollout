#!/usr/bin/env python3
import sys
print(sys.path)
import pytest
from eks_node_rollout import *
from botocore.stub import Stubber, ANY
import botocore.exceptions
from unittest.mock import Mock, patch
from click.testing import CliRunner


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


@patch('eks_node_rollout.get_latest_lt_version', return_value="1")
def test_describe_nodes_not_matching_lt(*args):
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
                        "LaunchTime": datetime.datetime.now() - datetime.timedelta(days=1),
                        "State": {
                            "Name": "pending"
                        }
                    },
                    {
                        'InstanceId': "bar",
                        "PrivateDnsName": "bar.aws.local",
                        "LaunchTime": datetime.datetime.now() - datetime.timedelta(days=2),
                        "State": {
                            "Name": "running"
                        }
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


@patch('eks_node_rollout.kubectl', create=True)
def test_wait_for_ready_node_rollout(*args):
    args[0].side_effect = [sh.ErrorReturnCode_1(full_cmd="foo", stdout="".encode(), stderr="blah blah NotFound blah".encode())]*20 + [None]
    start_time = datetime.datetime.now(datetime.timezone.utc)
    assert wait_for_ready_node("somenode") is None
    end_time = datetime.datetime.now(datetime.timezone.utc)
    duration = end_time - start_time
    assert duration > datetime.timedelta(seconds=3)


@patch('boto3.client', return_value=None)
@patch('time.sleep', return_value=None)
@patch('eks_node_rollout.get_matching_asgs', return_value=["asg1", "asg2", "asg3"])
@patch('eks_node_rollout.describe_nodes_not_matching_lt', return_value=[  # same instances each of the 3 ASGs
        {"PrivateDnsName": "instance1", "InstanceId": "i-asdfasdfasdf"},
        {"PrivateDnsName": "instance2", "InstanceId": "i-fdsaasdfdsasdf"},
        {"PrivateDnsName": "instance3", "InstanceId": "i-dsadfasdfdsafa"}
    ]
)
@patch('eks_node_rollout.check_is_cluster_autoscaler_tag_present', return_value=True)
@patch('eks_node_rollout.disable_autoscaling', return_value=None)
@patch('eks_node_rollout.get_num_of_instances', side_effect=[3, 4]*9)  # function is run twice for each of the 9 instances
@patch('eks_node_rollout.add_node', return_value=None)
@patch('eks_node_rollout.get_latest_instance', return_value={"PrivateDnsName": "instance4"})
@patch('eks_node_rollout.wait_for_ready_node', return_value=None)
@patch('eks_node_rollout.kubectl', return_value="evicting pod foobar", create=True)
@patch('eks_node_rollout.terminate_node', return_value=None)
@patch('eks_node_rollout.enable_autoscaling', return_value=None)
def test_rollout_nodes_happy(*args):
    cluster_name = "dev-apse2-main"
    runner = CliRunner()
    result = runner.invoke(rollout_nodes, [f"--cluster-name={cluster_name}"])
    assert result.exit_code == 0
    assert result.output is not None
