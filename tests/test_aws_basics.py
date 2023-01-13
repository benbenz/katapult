from .aws_patch import mock_make_api_call
from unittest.mock import patch
import pytest
from moto import mock_ec2
from .aws_config import ec2 , aws_credentials
import boto3

config = {
    'project'      : 'test' ,                             
    'maestro'      : 'local',
    'profile'      : 'mock' ,

    'instances' : [
        {
            'type' : 't3.micro' ,
            'number'       : 1
        }
    ]
}

@mock_ec2
def test_client_create(ec2):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        from cloudsend.provider import get_client

        cs = get_client(config)

        assert cs is not None

# working
# @mock_ec2
# def test_client_create():
#     client = boto3.client('ec2',region_name="eu-west-3")
#     result = client.describe_images()
#     print(result)
