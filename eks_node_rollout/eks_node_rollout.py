#!/usr/bin/env python3
import os
import sys
import click
from sh import kubectl
import sh
import datetime
from dateutil.tz import tzutc
import boto3
from pprint import pprint
import logging
import backoff
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logging.getLogger('sh').setLevel(logging.CRITICAL)


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
    logging.info(f"Launched a new node in ASG {asg_name}")


def get_latest_lt_version(ec2_client, lt_id):
    response = ec2_client.describe_launch_templates(
        LaunchTemplateIds=[
            lt_id
        ]
    )
    latest_version = response['LaunchTemplates'][0]['LatestVersionNumber']
    return latest_version


def describe_nodes_not_matching_lt(asg_client, ec2_client, asg_name):
    """Get information about outdated instances"""

    old_lt_instance_ids = []
    instances = []

    response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            asg_name
        ]
    )
    lt_id = response["AutoScalingGroups"][0]["MixedInstancesPolicy"]["LaunchTemplate"]["LaunchTemplateSpecification"]["LaunchTemplateId"]
    latest_lt = get_latest_lt_version(ec2_client, lt_id)
    logging.info(f"Latest launch template version is {latest_lt}")

    lt_info = [{instance["InstanceId"]: instance["LaunchTemplate"]["Version"]} for instance in response["AutoScalingGroups"][0]["Instances"]]
    logging.info(f"Instances and their Launch Templates: {lt_info}")

    old_lt_instance_ids = [instance["InstanceId"] for instance in response["AutoScalingGroups"][0]["Instances"] if int(instance["LaunchTemplate"]["Version"]) != latest_lt]
    if len(old_lt_instance_ids) == 0:
        logging.debug(f"Found no outdated instances.")
        return []

    response = ec2_client.describe_instances(InstanceIds=old_lt_instance_ids)
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append(instance)

    node_info = [instance["PrivateDnsName"] for instance in instances if instance["State"]["Name"] in ["pending", "running"]]
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


@backoff.on_predicate(backoff.expo)
def get_latest_instance(asg_client, ec2_client, asg_name, add_time, dry_run=True):
    """Retrieve the most recently launched/launching instance. Note that this is not necessarily the same one that was launched by `add_node()`, but it's the best I could think of"""

    instances = []

    response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            asg_name
        ]
    )
    instance_ids = [instance["InstanceId"] for instance in response["AutoScalingGroups"][0]["Instances"]]

    response = ec2_client.describe_instances(InstanceIds=instance_ids)
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append(instance)
    instance_launch_times = [{x["PrivateDnsName"]: x["LaunchTime"]} for x in instances]
    logging.debug(f"Node added at {add_time}")
    logging.debug(f"Instance launch times: {instance_launch_times}")
    if not dry_run:
        instances_valid = [instance for instance in instances if instance["State"]["Name"] in ["pending", "running"] and instance["LaunchTime"] > add_time]
    else:
        instances_valid = [instance for instance in instances if instance["State"]["Name"] in ["pending", "running"]]  # just grab any old instance to make `kubectl wait` work

    try:
        latest_instance = sorted(instances_valid, key=lambda instance: instance["LaunchTime"])[-1]
    except IndexError:
        return None  # backoff.on_predicate will retry if None is returned
    logging.info(f"Most recently launched instance is {latest_instance['PrivateDnsName']}")

    return latest_instance


def get_num_of_instances(asg_client, ec2_client, asg_name):
    """Returns number of instances in an ASG"""

    instances = []

    response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            asg_name
        ]
    )
    instance_ids = [instance["InstanceId"] for instance in response["AutoScalingGroups"][0]["Instances"]]
    response = ec2_client.describe_instances(InstanceIds=instance_ids)
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append(instance)
    instances = [instance for instance in instances if instance["State"]["Name"] in ["running", "pending"]]
    logging.debug(f"get_num_of_instances() returns {instances}")
    return len(instances)


def get_matching_asgs(asg_client, cluster_name):
    response = asg_client.describe_auto_scaling_groups()
    matching = []
    for asg in response["AutoScalingGroups"]:
        for tag in asg["Tags"]:
            if tag["Key"] == f"kubernetes.io/cluster/{cluster_name}":
                asg_name = asg["AutoScalingGroupName"]
                logging.info(f"Found matching ASG: {asg_name}")
                matching.append(asg)
    matching_names = [x["AutoScalingGroupName"] for x in matching]
    return matching_names


@backoff.on_predicate(backoff.expo)
def wait_for_ready_node(node_name):
    try:
        kubectl.wait("--for", "condition=Ready", f"node/{node_name}", "--timeout=300s")
    except sh.ErrorReturnCode_1 as e:
        if "NotFound" in e.stderr.decode():  # if the node has not even been registered in the API server yet, retry the command with backoff
            return None
        else:
            raise
    return True


@click.command()
@click.option('--cluster-name', envvar='EKS_NODE_ROLLOUT_CLUSTER_NAME', required=True, help="Cluster name to discover ASGs from")
@click.option('--dry-run/--no-dry-run', envvar='EKS_NODE_ROLLOUT_DRY_RUN', default=False, help="Run with read-only API calls")
@click.option('--debug/--no-debug', envvar='EKS_NODE_ROLLOUT_DEBUG', default=False, help="Enable debug logging")
def rollout_nodes(cluster_name, dry_run, debug):
    """Retrieve all outdated workers and perform a rolling update on them."""

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if dry_run:
        logging.info("--dry-run is enabled, only running read-only API calls")

    asg_client = boto3.client("autoscaling")
    ec2_client = boto3.client("ec2")

    asg_names = get_matching_asgs(asg_client=asg_client, cluster_name=cluster_name)

    for asg_name in asg_names:
        logging.info(f"Beginning rolling updates on ASG {asg_name}...")
        instances = describe_nodes_not_matching_lt(asg_client=asg_client, ec2_client=ec2_client, asg_name=asg_name)

        response = asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[
                asg_name
            ]
        )
        # check if cluster-autoscaler tag exists to begin with as we will set the value later on
        is_cluster_autoscaler_tag_present = len([x for x in response["AutoScalingGroups"][0]["Tags"] if x["Key"] == "k8s.io/cluster-autoscaler/enabled"]) > 0
        logging.info(f"cluster-autoscaler detected on {asg_name}: {is_cluster_autoscaler_tag_present}.")

        if is_cluster_autoscaler_tag_present:
            # prevent cluster-autoscaler from interrupting our rollout
            logging.info(f"Suspending cluster-autoscaler on {asg_name}...")
            if not dry_run:
                asg_client.delete_tag(
                    Tags=[
                        {
                            'ResourceId': asg_name,
                            'ResourceType': "auto-scaling-group",
                            'Key': "k8s.io/cluster-autoscaler/enabled"
                        },
                    ]
                )

        try:
            for instance in instances:
                before_instance_count = 0
                after_instance_count = 0

                before_instance_count = get_num_of_instances(asg_client=asg_client, ec2_client=ec2_client, asg_name=asg_name)
                add_time = datetime.datetime.now(datetime.timezone.utc)
                add_node(asg_client=asg_client, asg_name=asg_name, dry_run=dry_run)
                logging.info(f'Waiting for instance to be created...')
                logging.info(f'Sleeping 25s before polling.')
                time.sleep(25)  # new instance takes a bit to show up in API, don't bother polling yet
                latest_instance = get_latest_instance(asg_client=asg_client, ec2_client=ec2_client, asg_name=asg_name, add_time=add_time, dry_run=dry_run)
                latest_node_name = latest_instance["PrivateDnsName"]
                logging.info(f'Waiting for instance {latest_node_name} to be "Ready"...')
                logging.info(f'Sleeping 25s before polling.')
                time.sleep(25)  # instance will never be ready before this, don't bother polling yet
                wait_for_ready_node(latest_node_name)
                logging.info(f'Node {latest_node_name} is now "Ready".')
                after_instance_count = get_num_of_instances(asg_client=asg_client, ec2_client=ec2_client, asg_name=asg_name)

                # because get_latest_instance() doesn't necessarily return the instance launched by add_node(), this is just a safety precaution to ensure we've actually launched a node
                logging.info(f"Had {before_instance_count} instances in {asg_name} before, now have {after_instance_count} instances")
                if not dry_run:
                    assert after_instance_count > before_instance_count

                node_name = instance["PrivateDnsName"]
                logging.info(f'Draining node {node_name} (--dry-run={dry_run})')
                output = kubectl.drain(node_name, "--force", "--delete-local-data=true", "--ignore-daemonsets=true", "--timeout=120s", f"--dry-run={dry_run}")
                print(output.stdout.decode().rstrip())

                terminate_node(asg_client, instance["InstanceId"], dry_run)
        except Exception:
            logging.critical(f"Failed to upgrade all nodes in {asg_name}.")
        finally:
            if is_cluster_autoscaler_tag_present:
                # always re-enable cluster-autoscaler even if we fail partway through
                logging.info(f"Re-enabling cluster-autoscaler on {asg_name}...")
                if not dry_run:
                    asg_client.create_or_update_tags(
                        Tags=[
                            {
                                'ResourceId': asg_name,
                                'ResourceType': "auto-scaling-group",
                                'Key': "k8s.io/cluster-autoscaler/enabled",
                                'Value': "true",
                                'PropagateAtLaunch': False
                            },
                        ]
                    )

        logging.info(f"All instances in {asg_name} are up to date.")

    logging.info(f"All instances in EKS cluster {cluster_name} are up to date.")

if __name__ == '__main__':
    rollout_nodes()
