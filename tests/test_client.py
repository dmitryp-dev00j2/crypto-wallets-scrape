import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from walletscrape.client import RpcClient, RpcError


@pytest.fixture
def client():
    return RpcClient(endpoint="https://eth-mainnet.example.com", max_retries=3, base_delay=0.001)


@pytest.mark.asyncio
async def test_rpc_success(client):
    payload = {"jsonrpc": "2.0", "id": 1, "result": "0x1234"}
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=payload),
            raise_for_status=MagicMock()
        )
        
        res = await client.call("eth_getBalance", ["0xabc", "latest"])
        assert res == "0x1234"
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_retry_on_429_status(client):
    resp_429 = MagicMock(
        status_code=429,
        headers={"Retry-After": "0"},
        raise_for_status=MagicMock(side_effect=httpx.HTTPStatusError("Rate limited", request=None, response=MagicMock(status_code=429)))
    )
    resp_200 = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"jsonrpc": "2.0", "id": 1, "result": "0x5678"}),
        raise_for_status=MagicMock()
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Fails twice with 429 then succeeds
        mock_post.side_effect = [resp_429, resp_429, resp_200]
        
        res = await client.call("eth_blockNumber", [])
        assert res == "0x5678"
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_rpc_layer_rate_limit_retry(client):
    # Alchemy/Infura sometimes return 200 OK with json error code -32005 (rate limit)
    rate_limit_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32005, "message": "limit exceeded"}
    }
    success_payload = {"jsonrpc": "2.0", "id": 1, "result": "0xaa"}
    
    resp_rate_limit = MagicMock(status_code=200, json=MagicMock(return_value=rate_limit_payload), raise_for_status=MagicMock())
    resp_ok = MagicMock(status_code=200, json=MagicMock(return_value=success_payload), raise_for_status=MagicMock())
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [resp_rate_limit, resp_ok]
        
        res = await client.call("eth_blockNumber", [])
        assert res == "0xaa"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_unrecoverable_rpc_error_raises_immediately(client):
    # Invalid params shouldn't be retried
    invalid_params_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32602, "message": "invalid params"}
    }
    resp = MagicMock(status_code=200, json=MagicMock(return_value=invalid_params_payload), raise_for_status=MagicMock())
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = resp
        
        with pytest.raises(RpcError) as exc_info:
            await client.call("eth_getBalance", ["not_an_address"])
        
        assert exc_info.value.code == -32602
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_exceed_max_retries(client):
    resp_503 = MagicMock(
        status_code=503,
        raise_for_status=MagicMock(side_effect=httpx.HTTPStatusError("Service Unavailable", request=None, response=MagicMock(status_code=503)))
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = resp_503
        
        with pytest.raises(httpx.HTTPStatusError):
            await client.call("eth_blockNumber", [])
        assert mock_post.call_count == 4  # 1 initial + 3 retries


@pytest.mark.asyncio
async def test_batch_call_partial_and_retry(client):
    # Quick check for Solana / EVM multicall batching
    batch_payload = [
        {"jsonrpc": "2.0", "id": 0, "result": "0x1"},
        {"jsonrpc": "2.0", "id": 1, "result": "0x2"}
    ]
    resp = MagicMock(status_code=200, json=MagicMock(return_value=batch_payload), raise_for_status=MagicMock())
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = resp
        calls = [("eth_getBalance", ["0x1", "latest"]), ("eth_getBalance", ["0x2", "latest"])]
        results = await client.batch_call(calls)
        
        assert results == ["0x1", "0x2"]
