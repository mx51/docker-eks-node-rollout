#!/usr/bin/env python3
import os
import sys
import click
from sh import kubectl
import datetime
import boto3
from pprint import pprint
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_node(asg_client, asg_name, dry_run=True):
    """Increment desired_count by 1"""

    response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            asg_name
        ]
    )
    old_capacity = response["AutoScalingGroups"][0]["DesiredCapacity"]
    new_capacity = old_capacity + 1
    logging.debug(f"Old capacity was {old_capacity}, setting to {new_capacity}")
    if dry_run is False:
        asg_client.set_desired_capacity(
            AutoScalingGroupName=asg_name,
            DesiredCapacity=new_capacity
        )
    else:
        logging.info(f"--dry-run is set, not scaling up {asg_name}")


def describe_nodes_not_matching_lt(asg_client, ec2_client, asg_name):
    """Get information about outdated instances"""

    old_lt_instance_ids = []

    response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            asg_name
        ]
    )
    latest_lt = response["AutoScalingGroups"][0]["MixedInstancesPolicy"]["LaunchTemplate"]["LaunchTemplateSpecification"]["LaunchTemplateId"]
    logging.info(f"Latest launch template ID is {latest_lt}")

    lt_info = [{instance["InstanceId"]: instance["LaunchTemplate"]["LaunchTemplateId"]} for instance in response["AutoScalingGroups"][0]["Instances"]]
    logging.info(f"Instances and their Launch Templates: {lt_info}")

    old_lt_instance_ids = [instance["InstanceId"] for instance in response["AutoScalingGroups"][0]["Instances"] if instance["LaunchTemplate"]["LaunchTemplateId"] != latest_lt]
    if len(old_lt_instance_ids) == 0:
        logging.debug(f"Found no outdated instances.")
        return None

    response = ec2_client.describe_instances(InstanceIds=old_lt_instance_ids)
    instances = response["Reservations"][0]["Instances"]

    node_info = [instance["PrivateDnsName"] for instance in instances]
    logging.info(f"Instances with outdated Launch Template: {node_info}")

    return instances


def terminate_node(asg_client, instance_id, dry_run=True):
    """Terminate a given instance"""

    if dry_run is False:
        logging.info(f"Terminating {instance_id}...")
        response = asg_client.terminate_instance_in_auto_scaling_group(
            InstanceId=instance_id,
            ShouldDecrementDesiredCapacity=True
        )
    else:
        logging.info(f"--dry-run is set, not actually terminating {instance_id}")


def get_latest_instance(asg_client, ec2_client, asg_name):
    """Retrieve the most recently launched/launching instance. Note that this is not necessarily the same one that was launched by `add_node()`, but it's the best I could think of"""

    old_lt_instance_ids = []

    response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            asg_name
        ]
    )
    instance_ids = [instance["InstanceId"] for instance in response["AutoScalingGroups"][0]["Instances"]]

    response = ec2_client.describe_instances(InstanceIds=instance_ids)
    instances = response["Reservations"][0]["Instances"]
    instances_valid = [instance for instance in instances if instance["State"]["Name"] in ["running", "pending"]]
    node_names = [instance["PrivateDnsName"] for instance in instances_valid]
    latest_instance = sorted(instances_valid, key=lambda instance: instance["LaunchTime"])[-1]
    logging.info(f"Most recently launched instance is {latest_instance['PrivateDnsName']}")

    return latest_instance


def get_num_of_instances(asg_client, asg_name):
    """Returns number of instances in an ASG"""

    response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            asg_name
        ]
    )
    instances = [instance for instance in instances if instance["State"]["Name"] in ["running", "pending"]]
    return len(instances)


@click.command()
@click.option('--asg-name', envvar='EKS_NODE_ROLLOUT_ASG_NAME', required=False, help="ASG name to roll")
@click.option('--dry-run/--no-dry-run', envvar='EKS_NODE_ROLLOUT_DRY_RUN', default=True, help="Run with read-only API calls.")
def rollout_nodes(asg_name, dry_run):
    """Retrieve all outdated workers and perform a rolling update on them."""

    if dry_run:
        logging.info("--dry-run is enabled, only running read-only API calls")

    asg_client = boto3.client("autoscaling")
    ec2_client = boto3.client("ec2")

    instances = describe_nodes_not_matching_lt(asg_client=asg_client, ec2_client=ec2_client, asg_name=asg_name)

    if instances is None:
        logging.info(f"All instances in {asg_name} are up to date, nothing to do!")
        return

    for instance in instances:
        before_instance_count = get_num_of_instances(asg_client=asg_client, asg_name=asg_name)
        add_node(asg_client=asg_client, asg_name=asg_name, dry_run=dry_run)
        latest_instance = get_latest_instance(asg_client=asg_client, ec2_client=ec2_client, asg_name=asg_name)
        logging.info(f'Waiting for instance {node_name} to be "Ready"')
        kubectl.wait("--for", "condition=Ready", f"node/{node_name}", "--timeout=300s")
        logging.info(f'Node {node_name} is now "Ready".')
        after_instance_count = get_num_of_instances(asg_client=asg_client, asg_name=asg_name)
        # because get_latest_instance() doesn't necessarily return the instance launched by add_node(), this is just a safety precaution to ensure we've actually launched a node
        assert before_instance_count > after_instance_count

        node_name = instance["PrivateDnsName"]
        logging.info(f'Draining node {node_name} (--dry-run={dry_run})')
        kubectl.drain(node_name, "--force", "--delete-local-data=true", "--ignore-daemonsets=true", "--timeout=30s", f"--dry-run={dry_run}")
        terminate_node(asg_client, instance["InstanceId"], dry_run)

    logging.info(f"All instances in {asg_name} have been updated.")


if __name__ == '__main__':
    rollout_nodes()
