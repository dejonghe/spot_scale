#!/usr/bin/env python

import boto3
import datetime
import dateutil

class test_context(dict):
    '''This is a text context object used when running function locally'''
    def __init__(self,profile,region):
        self.profile = profile
        self.region = region

class ecs_space_metric(object):
    def __init__(self, event, context):
        print(event)
        self.cluster = event['Cluster']
        self.session = self.setup_session(context)
        self.ecs = self.session.client('ecs')
        self.cw = self.session.client('cloudwatch')

    def run(self):
        self.lcpu, self.lmem = self.find_largest_container(self.cluster)
        self.availability = self.get_availability()
        self.push_metric()

    def setup_session(self,context):
        '''
        Checks to see if running locally by use of test_context
        If so use profile and region from test_context
        If not let use default session
        '''
        if isinstance(context,test_context):
            # For testing use profile and region from test_context
            print('Using test_context')
            print("Profile: {}".format(context.profile))
            print("Region: {}".format(context.region))
            self.test = True
            return boto3.session.Session(profile_name=context.profile,region_name=context.region)
        else:
            # Sets up the session in lambda context
            return boto3.session.Session()

    def find_largest_container(self,cluster):
        services = self.ecs.list_services(cluster=cluster)
        cpu,mem = 0,0
        for service in services['serviceArns']:
            service_detail = self.ecs.describe_services(cluster=cluster,services=[service])['services'][0]
            task_def = self.ecs.describe_task_definition(taskDefinition=service_detail['taskDefinition'])['taskDefinition']
            for container in task_def['containerDefinitions']:
                if container['cpu'] > cpu and container['memory'] > mem:
                    cpu = container['cpu']
                    mem = container['memory']
        return (cpu,mem)
            
    def get_availability(self):
        instance_list = self.ecs.list_container_instances(cluster=self.cluster, status='ACTIVE')
        print(instance_list)
        instances = self.ecs.describe_container_instances(cluster=self.cluster,
                                                          containerInstances=instance_list['containerInstanceArns'])

        schedulable_containers = 0
        for instance in instances['containerInstances']:
            remaining_resources = {resource['name']: resource for resource in instance['remainingResources']}
            containers_by_cpu = int(remaining_resources['CPU']['integerValue'] / self.lcpu)
            containers_by_mem = int(remaining_resources['MEMORY']['integerValue'] / self.lmem)
            schedulable_containers += min(containers_by_cpu, containers_by_mem)
            print('%s containers could be scheduled on %s based on CPU only' % (containers_by_cpu, instance['ec2InstanceId']))
            print('%s containers could be scheduled on %s based on memory only' % (containers_by_mem, instance['ec2InstanceId']))
        return schedulable_containers

    def push_metric(self):
        self.cw.put_metric_data(Namespace='AWS/ECS',
                       MetricData=[{
                           'MetricName': 'SchedulableContainers',
                           'Dimensions': [{
                               'Name': 'ClusterName',
                               'Value': self.cluster
                           }],
                           'Timestamp': datetime.datetime.now(dateutil.tz.tzlocal()),
                           'Value': self.availability
                       }])

def lambda_handler(event, context):
    space = ecs_space_metric(event,context)
    space.run()
    return {}
