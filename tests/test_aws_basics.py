from unittest.mock import patch
import boto3
from moto import mock_s3
from cloudsend.provider import get_client
from .aws_patch import mock_make_api_call

config = {
    'project'      : 'test' ,                             
    'maestro'      : 'local',

    'instances' : [
        {
            'type' : 't3.micro' ,
            'number'       : 1
        }
    ]
}

# def test_list_findings():
#     client = boto3.client("accessanalyzer")

#     with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
#         analyzers_list = client.list_analyzers()
#         assert len(analyzers_list["analyzers"]) == 1
#         # include your assertions here

@mock_s3
def test_client_create():
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        cs = get_client(config)

        assert cs is not None

        #cs.start()