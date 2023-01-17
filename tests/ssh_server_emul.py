"""A pytest fixture for running an ssh mock server.

Requires pytest and asyncssh:

    $ pip install pytest asyncssh 
"""

from socket import AF_INET
from unittest.mock import Mock
from contextlib import asynccontextmanager
from asyncio.subprocess import create_subprocess_exec, PIPE
from katapult.core import *

import pytest
import asyncssh
import sys
import os
from datetime import datetime
import re
import asyncio
import random

from io import StringIO 

MKCFG_REUPLOAD = 'reupload'

random.seed(10)


class NoAuthSSHServer(asyncssh.SSHServer):
    """An ssh server without authentification."""

    def begin_auth(self, username):
        return False

    def connection_made(self, conn):
        print('SSH connection received from %s.' %
                  conn.get_extra_info('peername')[0])

    def connection_lost(self, exc):
        if exc:
            if isinstance(exc,BrokenPipeError):
                print('SSH connection error (broken pipe):' + str(exc), file=sys.stderr)
            else:
                print('SSH connection error: ' + str(exc), file=sys.stderr)
        else:
            print('SSH connection closed.') 

class MySFTPServer(asyncssh.SFTPServer):

    def __init__(self,ssh_server):
        self._ssh_server = ssh_server

    #def __init__(self, chan):
    def __call__(self, chan):
        #root = '/tmp/sftp/' + chan.get_extra_info('username')
        #os.makedirs(root, exist_ok=True)
        #super().__init__(chan, chroot=root)            
        #super().__init__(chan)
        #return self
        nu_server = MySFTPServer(self._ssh_server)
        asyncssh.SFTPServer.__init__(nu_server,chan)
        return nu_server

    def open(self, path, pflags, attrs):
        #print("open",path)
        iofile = StringIO()
        #return super().open(path, pflags, attrs)
        self._ssh_server.files[path.decode()] = iofile
        return iofile

    def close(self, file_obj):
        #print("close",file_obj)
        file_obj.seek(0)
        file_content = file_obj.read()
        for k,v in self._ssh_server.files.items():
            if v is file_obj:
                self._ssh_server.files[k] = file_content
                break
        super().close(file_obj)


    def read(self, file_obj, offset, size):
        #print("read",file_obj)
        super().read(file_obj,offset, size)

    def write(self, file_obj, offset, data):
        #print("write",file_obj)
        if isinstance(data,bytearray) or isinstance(data,bytes):
            data = data.decode()
        super().write(file_obj,offset, data)

class SSHServerEmul:

    def __init__(self):

        self.config   = dict()
        self.hostname = 'localhost'
        self.port     = 0 
        self.privkey  = None
        self.sftp_server = None
        self.server = None
        self.job_period = 5
        self.files  = dict()
        self.batches = dict()

    async def listen(self,port=0):
        
        self.privkey = asyncssh.generate_private_key("ssh-rsa")

        acceptor = await asyncssh.listen(
            self.hostname,
            0,
            server_factory=NoAuthSSHServer,
            server_host_keys=[self.privkey],
            process_factory=self.handler,
            sftp_factory=MySFTPServer(self),
            options=asyncssh.SSHServerConnectionOptions(host_based_auth=False)
        )
        self.server = acceptor._server
        self.sftp_server = acceptor._options.sftp_factory
        self.port = next(
            socket.getsockname()[1]
            for socket in self.server.sockets
            if socket.family == AF_INET
        )  

    def set_job_period(self,value):
        self.job_period = value

    async def run_batch(self,batch):
        processes = batch['processes']
        for process in processes:    
            command = process['command']
            if 'err_mem' in command:
                process['state'] = 'aborted(OOM kill)'
                continue
            elif 'err' in command:
                process['state'] = 'aborted(script error)'
                continue
            elif 'err' in process['env_name']:
                process['state'] = 'aborted(environment error)'
                continue
            else:
                process['state'] = 'running(normally)'            
            await asyncio.sleep(self.job_period)
            process['state'] = 'done(normally)'

    def start_batch(self,uid):
        batch = self.batches[uid]
        batch['future'] = asyncio.ensure_future(self.run_batch(batch))
    
    async def wait_for_batches(self):
        group = []
        for uid,batch in self.batches.items():
            if batch.get('future'):
                group.append(batch['future'])
        await asyncio.gather(*group)
        print("done")

    def get_return_value(self,process):
        # get the return_value set by ssh_mock_server.return_value (from the test)
        # always force re-upload
        cmd = process.command

        # re-upload query
        # TODO: add more control/granularity
        if 'ready' in cmd and '"ok"' in cmd:
            if self.config.get(MKCFG_REUPLOAD,True):
                return "not_ok"
            else:
                return "ok"
        # pyyaml install
        elif cmd.strip() == 'pip install pyyaml':
            return ""
        # making .sh executables
        elif 'chmod +x' in cmd:
            return ""
        # EOL thing.            
        elif "sed -i -e 's/\r$//' " in cmd:
            return ""
        # configure the environment
        elif 'run/config.py' in cmd:
            return ""
        # bootstrap env
        elif 'generate_envs.sh' in cmd:
            return ""
        # reset directory / ready
        elif 'mkdir' in cmd and 'rm' in cmd and 'ready' in cmd:
            return ""
        # misc. directory manip
        elif 'mkdir' in cmd:
            return ""
        # remove ready
        elif 'rm' in cmd and 'ready' in cmd:
            return ""
        # the execution of the batch
        elif 'rm' in cmd and 'out.log' in cmd and 'batch_run' in cmd:
            # batch_run-1619b8a5eb424da08945c2b6134879d1.sh
            result = re.search(r"batch_run\-([0-9a-zA-Z]+)\.sh", cmd)
            uid    = result.group(1)
            batch_path = re.search(r"\;(.*batch_run\-[0-9a-zA-Z]+\.sh)", cmd).group(1)
            batch_content = self.files.get(batch_path)
            # remove rm's and mkdir's
            batch_content = re.sub(r"^rm .*$\n","",batch_content,flags=re.M)
            batch_content = re.sub(r"^mkdir .*$\n","",batch_content,flags=re.M)
            batch_lines   = batch_content.split('\n')

            processes  = list()
            instance   = None
            notossep   =  "[^"+os.sep+"]+"
            notossep_g = "([^"+os.sep+"]+)"
            spaced_arg_q = r'\s+\"(.*)\"'
            spaced_arg   = r'\s+([a-zA-Z0-9]+)'
            r_path = os.path.join("("+kt_instanceNameRoot+notossep+")",'run',notossep_g,notossep_g,notossep_g)
            regex_find_info    = r"" + r_path
            regex_find_state   = r"echo '([^']+)'\s*>\s*.*" + os.path.join(r_path,'state')
            # envwithhas - command - input files - output files - batch uid - jobhash - uid
            regex_find_more = r"" + os.path.join('run','run.sh') + spaced_arg_q + spaced_arg_q + spaced_arg_q + spaced_arg_q + spaced_arg + spaced_arg + spaced_arg
            for line in batch_lines:
                if line.startswith('ln'):
                    continue
                elif line.startswith('echo'):
                    match    = re.search(regex_find_info, line)
                    instance = match.group(1)
                    env_name = match.group(2)
                    job_hash = match.group(3)
                    proc_uid = match.group(4)
                    statem   = re.search(regex_find_state, line)
                    state    = statem.group(1)
                    processes.append( {
                            'uid'      : proc_uid ,
                            'env_name' : env_name ,
                            'job_hash' : job_hash ,
                            'state'    : state ,
                            'instance' : instance
                    })
                elif 'run.sh' in line:
                    moreinfo  = re.search(regex_find_more, line)
                    env_name2 = moreinfo.group(1)
                    command   = moreinfo.group(2)
                    input_files = moreinfo.group(3).split('|')
                    output_files = moreinfo.group(4).split('|')
                    batch_uid = moreinfo.group(5)
                    job_hash2 = moreinfo.group(6)
                    proc_uid2 = moreinfo.group(7)
                    proc = next((x for x in processes if x['uid']==proc_uid2))
                    if not proc:
                        raise Error('internal error: this shouldnt happen (2)')
                    assert proc['env_name'] == env_name2
                    assert proc['job_hash'] == job_hash2
                    proc['batch_uid']    = batch_uid
                    proc['input_files']  = input_files
                    proc['output_files'] = output_files
                    proc['command']      = command
            
            b_uid_key = instance+":"+uid
            self.batches[b_uid_key] = {
                'start_time' : datetime.now() ,
                'file' : batch_path ,
                'content' : batch_content ,
                'processes' : processes ,
                'instance' : instance
            }
            self.start_batch(b_uid_key)
            return ""
        elif 'state.sh' in cmd:
            cmd_result = ""
            result = re.findall(r"\"([^\"]+)\" ([0-9a-zA-Z]+) ([0-9a-zA-Z]+) ([0-9]+|None) ([0-9]+|None) \"([^\"]+)\"",cmd)
            for r in result:
                env_name  = r[0]
                job_hash  = r[1]
                proc_uid  = r[2]
                proc_pid1 = r[3]
                proc_pid2 = r[4]
                outputs   = r[5].split('|')
                proc      = None
                for buid , batch in self.batches.items():
                    processes = batch['processes']
                    try:
                        proc = next((x for x in processes if x['uid']==proc_uid))
                        if proc:
                            break
                    except StopIteration as e:
                        # we didnt find the process in this instance's batch
                        pass
                if not proc:
                    cmd_result += "{0},{1},{2},{3}\n".format(proc_uid,None,"unknown",None)
                    continue
                if proc_pid1 == 'None':
                    proc['pid1'] = random.randint(0,7000)
                    proc['pid2'] = None
                if ('running' in proc['state'] or 'done' in proc['state']) and proc['pid2'] is None:
                    proc['pid2'] = random.randint(0,7000)
                elif 'aborted' in proc['state'] and 'script error' in proc['state'] and proc['pid2'] is None:
                    proc['pid2'] = random.randint(0,7000)
                cmd_result += "{0},{1},{2},{3}\n".format(proc['uid'],proc['pid1'],proc['state'],proc['pid2'])
            return cmd_result
        # otherwise
        else:
            print("USING DEFAULT COMMAND ANSWER !")
            return ""

    def handler(self,process):
        value = self.get_return_value(process)
        process.stdout.write(value)
        process.exit(0)

    def file_exists(self,path):
        return path in self.config

    def num_files(self):
        return len(self.files.values())

    def set_config(self,key,val):
        self.config[key] = val

    def has_file(self,instance,filename):
        for file_path in self.files.keys():
            if instance.get_name() in file_path and filename in file_path:
                return True
        return False
