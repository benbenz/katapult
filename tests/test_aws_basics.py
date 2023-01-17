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
from katapult.core import KatapultInstanceState , KatapultProcessState
from .ssh_server_mock import ssh_mock_server , MKCFG_REUPLOAD
from .ssh_server_emul import SSHServerEmul
from katapult.providerfat import RUNNER_FILES , set_sleep_period
from pathlib import Path

TEST_PERIOD = 0.5

def check_file_uploaded(ssh_server,instance,file_list,ref_file,split=False):
    if not file_list:
        return
    if ref_file:
        ref_file = ref_file.split()
        ref_file = ref_file[0]
        ref_file_path = Path(ref_file)
        ref_file_dir = ref_file_path.parent.absolute()
    else:
        ref_file_dir = os.getcwd()

    if split:
        args = file_list.split()
        file_list = args[0]
        is_file = os.path.isfile(file_list) if ref_file_dir is None else os.path.isfile(os.path.join(ref_file_dir,file_list))
        if is_file:
            assert ssh_server.has_file( instance , file_list )
        else:
            print('skipping test for uploaded due to missing file',file_list)
    else:
        if not isinstance(file_list,list):
            file_list = [ file_list ]
        for f in file_list:
            is_file = os.path.isfile(f) if ref_file_dir is None else os.path.isfile(os.path.join(ref_file_dir,f))
            if is_file:
                assert ssh_server.has_file( instance , f )
            else:
                print('skipping test for uploaded due to missing file',f)

@mock_ec2
@pytest.mark.asyncio
async def test_client_create_one_instance(ec2):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        from katapult.provider import get_client

        kt = get_client(config_aws_one_instance_local)

        assert kt is not None

        objs = await kt.get_objects()

        assert objs.get('instances') is not None

        assert len(objs.get('instances')) == 1

@mock_ec2
@pytest.mark.asyncio
async def test_client_create_full(ec2):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        from katapult.provider import get_client

        kt = get_client(os.path.join('tests','config.example.all_tests.local.py'))

        assert kt is not None

        objs = await kt.get_objects()

        assert objs.get('instances') is not None

        assert len(objs.get('instances')) == 2

        assert len(objs.get('environments')) == 7

        assert len(objs.get('jobs')) == 12


@mock_ec2
@mock_sts
@pytest.mark.asyncio
async def test_client_start(ec2,sts):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):
        from katapult.provider import get_client

        kt = get_client(os.path.join('tests','config.example.all_tests.local.py'))

        await kt.start()

        objects = await kt.get_objects()

        for instance in objects['instances']:
            await kt._wait_for_instance(instance)

        for instance in objects['instances']:
            assert instance.get_state() == KatapultInstanceState.RUNNING


@mock_ec2
@mock_sts
#@patch('katapult.aws.AWSKatapultFatProvider',spec=True)
@pytest.mark.asyncio
#async def test_client_deploy(mock_katapult,ec2,sts,ssh_mock_server):
#async def test_client_deploy(ec2,sts,ssh_mock_server):
async def test_client_deploy(ec2,sts):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):

        from katapult.provider import get_client

        kt = get_client(os.path.join('tests','config.example.all_tests.local.py'))

        await kt.start()

        # configure the server
        ssh_server = SSHServerEmul()
        await ssh_server.listen()
        ssh_server.set_config(MKCFG_REUPLOAD,True) # will always reupload files

        # attach the server to the client
        kt.set_mock_server(ssh_server)

        await kt.deploy()

        objs = await kt.get_objects()

        assert len(objs.get('instances')) == 2

        instances = objs['instances']

        for runner_file in RUNNER_FILES:
            for instance in instances:
                assert ssh_server.has_file( instance , runner_file )

        # this is a fat client so we have the full objects handy
        assert len(objs.get('jobs')) == 12

        for job in objs['jobs']:
            instance = job.get_instance()
            check_file_uploaded(ssh_server,instance,job.get_config('run_script'),None,True)
            check_file_uploaded(ssh_server,instance,job.get_config('upload_files'),job.get_config('run_script'),False)
            check_file_uploaded(ssh_server,instance,job.get_config('input_files'),job.get_config('run_script'),False)



@mock_ec2
@mock_sts
@pytest.mark.asyncio
async def test_client_run(ec2,sts):
    with patch('botocore.client.BaseClient._make_api_call', new=mock_make_api_call):

        from katapult.provider import get_client

        kt = get_client(os.path.join('tests','config.example.all_tests.local.py'))

        await kt.start()

        # configure the server
        ssh_server = SSHServerEmul()
        await ssh_server.listen()
        ssh_server.set_config(MKCFG_REUPLOAD,True) # will always reupload files

        # attach the server to the client
        kt.set_mock_server(ssh_server)

        await kt.deploy()
        
        # set the fat provider sleep period to 0.5s (instead of 15s)
        set_sleep_period(TEST_PERIOD/2) 
        ssh_server.set_job_period(TEST_PERIOD)

        await kt.run()   

        # always make sure the futures of the batches are completed
        await ssh_server.wait_for_batches()  

        # make sure we update one last time
        await kt.get_jobs_states()
        # just for good measure
        await kt.wait(KatapultProcessState.DONE|KatapultProcessState.ABORTED)

        objs = await kt.get_objects()

        # this is the fat client so we have all info available (no proxies)
        jobs = objs['jobs']

        for job in jobs:
            dpl_job = job.get_deployed_jobs()
            assert dpl_job and len(dpl_job)==1
            dpl_job = dpl_job[0]
            command = dpl_job.get_command()
            process = job.get_last_process()
            assert process
            substate = process.get_substate()
            if substate:
                substate = substate.lower()
            state = process.get_state()
            if 'err_mem' in command:
                assert state == KatapultProcessState.ABORTED
                assert 'oom' in  substate or 'memory' in substate
            elif 'err' in command:
                assert state == KatapultProcessState.ABORTED
            elif 'err' in job.get_env().get_name():
                assert state == KatapultProcessState.ABORTED
                assert 'env' in substate
            else:
                assert state == KatapultProcessState.DONE

# working
# @mock_ec2
# def test_client_create():
#     client = boto3.client('ec2',region_name="eu-west-3")
#     result = client.describe_images()
#     print(result)
