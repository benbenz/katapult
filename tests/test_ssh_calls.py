import pytest
from .ssh_server_mock import ssh_mock_server

# Tests

@pytest.mark.asyncio
async def test(ssh_mock_server):
    """Demonstrate the use the ssh_mock_server fixture."""
    ssh_mock_server.return_value = "test"
    process = await ssh_mock_server.run_mock_shell("ssh localhost echo test")
    stdout, stderr = await process.communicate()
    errors = stderr.decode()
    assert stdout.decode() == "test"
    ssh_mock_server.assert_called_once_with("echo test")
