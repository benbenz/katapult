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


class NoAuthSSHServer(asyncssh.SSHServer):
    """An ssh server without authentification."""

    def begin_auth(self, username):
        return False


@asynccontextmanager
async def simple_ssh_server(handler, port=0):
    """Run a simple ssh server from a provided handler."""

    private_key = asyncssh.generate_private_key("ssh-rsa")
    server = await asyncssh.create_server(
        NoAuthSSHServer,
        "localhost",
        0,
        server_host_keys=[private_key],
        process_factory=handler,
    )
    port = next(
        socket.getsockname()[1]
        for socket in server.sockets
        if socket.family == AF_INET
    )
    async with server:
        yield port , private_key


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

    def handler(process):
        #value = mock(process.get_command())
        value = mock(process.command)
        process.stdout.write(value)
        process.exit(0)

    async with simple_ssh_server(handler) as port_private_key:
        port = port_private_key[0]
        private_key = port_private_key[1]
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

        mock.run_mock_shell = run_mock_shell
        mock.port = port 
        mock.private_key = private_key
        yield mock
