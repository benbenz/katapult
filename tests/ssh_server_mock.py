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
    def __init__(self, chan):
        #root = '/tmp/sftp/' + chan.get_extra_info('username')
        #os.makedirs(root, exist_ok=True)
        #super().__init__(chan, chroot=root)            
        super().__init__(chan)
        self._files = dict()

    def open(self, path, pflags, attrs):
        #print("open",path)
        iofile = StringIO()
        #return super().open(path, pflags, attrs)
        self._files[path] = iofile
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

@asynccontextmanager
async def simple_ssh_server(handler, port=0):
    """Run a simple ssh server from a provided handler."""

    private_key = asyncssh.generate_private_key("ssh-rsa")
    # server = await asyncssh.create_server(
    #     NoAuthSSHServer,
    #     "localhost",
    #     0,
    #     server_host_keys=[private_key],
    #     process_factory=handler,
    # )
    acceptor = await asyncssh.listen(
        "localhost",
        0,
        server_factory=NoAuthSSHServer,
        server_host_keys=[private_key],
        process_factory=handler,
        sftp_factory=MySFTPServer,
        options=asyncssh.SSHServerConnectionOptions(host_based_auth=False)
    )
    server = acceptor._server
    port = next(
        socket.getsockname()[1]
        for socket in server.sockets
        if socket.family == AF_INET
    )
    async with server:
        yield port , private_key , acceptor


@pytest.fixture(scope="function")
@pytest.mark.asyncio
async def ssh_mock_server():
    """A pytest fixture to run an ssh mock server.

    The returned mock is called with the provided command for every
    connection to the ssh server. A return value may be specified
    using:

        ssh_mock_server.return_value = "some result"

    This return value represents the stdout output of the command.
    In order to run a shell command, use the `run_mock_shell` method:

        process = await ssh_mock_server.run_mock_shell(
            "ssh localhost command")

    The shell command runs in a context where ssh is configured
    to connect transparently to the ssh mock server. The returned
    process is an asyncio subprocess and is used as follow:

        stdout, stderr = await process.communicate(stdin)
    """
    mock = Mock(name="ssh_mock_server")

    def get_return_value(process):
        # get the return_value set by ssh_mock_server.return_value (from the test)
        # always force re-upload
        cmd = process.command

        # re-upload query
        # TODO: add more control/granularity
        if 'ready' in cmd and '"ok"' in cmd:
            if mock.config.get(MKCFG_REUPLOAD,True):
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

        return mock(process.command)

    def handler(process):
        #value = mock(process.get_command())

        #value = mock(process.command)
        sftp_server = mock.sftp_server

        value = get_return_value(process)
        process.stdout.write(value)
        process.exit(0)

    async with simple_ssh_server(handler) as server_stuff:
        port = server_stuff[0]
        private_key = server_stuff[1]
        acceptor = server_stuff[2]
        sftp_server = acceptor._options.sftp_factory
        ssh_options = [
            "-o UserKnownHostsFile=/dev/null",
            "-o StrictHostKeyChecking=no",
            f"-p {port}",
        ]
        ssh_alias = " ".join(["ssh"] + ssh_options)

        async def run_mock_shell(command, **kwargs):
            bash_commands = [
                "shopt -s expand_aliases",
                f"alias ssh={ssh_alias!r}",
                command,
            ]
            return await create_subprocess_exec(
                "/bin/bash",
                "-c",
                "\n".join(bash_commands),
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
                **kwargs,
            )

        def file_exists(path):
            return path in mock.config

        def num_files():
            return len(mock.config.values())

        mock.run_mock_shell = run_mock_shell
        mock.file_exists    = file_exists
        mock.port           = port 
        mock.private_key    = private_key
        mock.hostname       = 'localhost'
        mock.sftp_server    = sftp_server
        mock.config         = dict()
        
        yield mock
