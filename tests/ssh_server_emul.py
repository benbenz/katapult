"""A pytest fixture for running an ssh mock server.

Requires pytest and asyncssh:

    $ pip install pytest asyncssh 
"""

from socket import AF_INET
from unittest.mock import Mock
from contextlib import asynccontextmanager
from asyncio.subprocess import create_subprocess_exec, PIPE

import pytest
import asyncssh
import sys
import os

from io import StringIO 

MKCFG_REUPLOAD = 'reupload'


class NoAuthSSHServer(asyncssh.SSHServer):
    """An ssh server without authentification."""

    def begin_auth(self, username):
        return False

    def connection_made(self, conn):
        print('SSH connection received from %s.' %
                  conn.get_extra_info('peername')[0])

    def connection_lost(self, exc):
        if exc:
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
        self.files  = dict()

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
        # otherwise
        else:
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
