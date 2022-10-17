import boto3

client = boto3.client('batch')

response = client.create_compute_environment(
    computeEnvironmentName='scriptflow_environment',
    type='MANAGED',
    state='ENABLED',
    computeResources={
        'type': 'EC2',
        'allocationStrategy': 'BEST_FIT',
        'minvCpus': 0,
        'maxvCpus': 256,
        'subnets': [
            'subnet-0ecaa08058826ec19',
        ],
        'instanceRole': 'ecsInstanceRole',
        'securityGroupIds': [
            'sg-ee90f586',
        ],
        'instanceTypes': [
            'optimal',
        ]
    }
)

print(response)