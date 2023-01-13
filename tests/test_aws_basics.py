from .aws_patch import mock_make_api_call
from unittest.mock import patch
import pytest
from moto import mock_ec2 , mock_sts
from .aws_config import ec2 , sts , aws_credentials
import boto3
import os
import pytest_asyncio
import asyncio
from .configs import config_aws_one_instance_local
from cloudsend.core import CloudSendInstanceState
from .ssh_server_mock import ssh_mock_server

@mock_ec2
def test_client_create_one_instance(ec2):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        from cloudsend.provider import get_client

        cs = get_client(config_aws_one_instance_local)

        assert cs is not None

        assert cs.get_objects().get('instances') is not None

        assert len(cs.get_objects().get('instances')) == 1

@mock_ec2
def test_client_create_full(ec2):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        from cloudsend.provider import get_client

        cs = get_client(os.path.join('tests','config.example.all_tests.local.py'))

        assert cs is not None

        assert cs.get_objects().get('instances') is not None

        assert len(cs.get_objects().get('instances')) == 2

        assert len(cs.get_objects().get('environments')) == 7

        assert len(cs.get_objects().get('jobs')) == 12


@mock_ec2
@mock_sts
@pytest.mark.asyncio
async def test_client_start(ec2,sts):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        from cloudsend.provider import get_client

        cs = get_client(os.path.join('tests','config.example.all_tests.local.py'))

        await cs.start()

        objects = cs.get_objects()

        for instance in objects['instances']:
            await cs._wait_for_instance(instance)

        for instance in objects['instances']:
            assert instance.get_state() == CloudSendInstanceState.RUNNING


@mock_ec2
@mock_sts
@pytest.mark.asyncio
async def test_client_deploy(ec2,sts,ssh_mock_server):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        from cloudsend.provider import get_client

        cs = get_client(os.path.join('tests','config.example.all_tests.local.py'))

        await cs.start()

        ssh_mock_server.return_value = "test"
        port = ssh_mock_server.port
        priv = ssh_mock_server.private_key
        cs.set_ssh_server('localhost',port,priv)

        await cs.deploy()

# working
# @mock_ec2
# def test_client_create():
#     client = boto3.client('ec2',region_name="eu-west-3")
#     result = client.describe_images()
#     print(result)
