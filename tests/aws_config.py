import pytest
import os
import boto3
from moto import mock_ec2 , mock_sts
from unittest import mock
from pathlib import Path

@pytest.fixture(scope="module")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-3"
    moto_credentials_file_path = Path(__file__).parent.absolute() / 'credentials'
    os.environ['AWS_SHARED_CREDENTIALS_FILE'] = str(moto_credentials_file_path)


@pytest.fixture(scope="function")
def ec2(aws_credentials):
    with mock_ec2():
        #yield boto3.client("ec2", region_name="eu-west-3")   
        session=boto3.Session(profile_name='mock',region_name="eu-west-3")
        yield session.client('ec2')

@pytest.fixture(scope="function")
def sts(aws_credentials):
    with mock_sts():
        #yield boto3.client("ec2", region_name="eu-west-3")   
        session=boto3.Session(profile_name='mock',region_name="eu-west-3")
        yield session.client('sts')

