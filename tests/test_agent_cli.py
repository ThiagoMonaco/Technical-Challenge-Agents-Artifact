from copy import deepcopy
import json
import logging
from types import SimpleNamespace

from openai import APIError
from openai import OpenAI
from openai.types.responses import Response
import httpx2
import pytest

from emporio.agent import API_FAILURE, ROUND_LIMIT, Agent
from emporio.cli import chat, main, make_agent
from emporio.tools import TOOLS


def response(output=None, status="completed"):
    return Response.model_validate({
        "id": "resp_test", "created_at": 0, "model": "gpt-5-mini", "object": "response",
        "status": status, "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        "output": output or [],
        "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 0}},
    })


def final(text="Olá! Como posso ajudar?"):
    return response([{"type": "message", "id": "msg_test", "role": "assistant", "status": "completed",
                      "content": [{"type": "output_text", "text": text, "annotations": []}]}])


def call(name="get_product_details", arguments='{"product_id":81}', call_id="call_1"):
    return {"type": "function_call", "id": "fc_test", "name": name,
            "arguments": arguments, "call_id": call_id, "status": "completed"}


class Responses:
    def __init__(self, items):
        self.items = iter(items)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        item = next(self.items)
        if isinstance(item, Exception):
            raise item
        return item


def agent(store, items, **kwargs):
    client = SimpleNamespace(responses=Responses(items))
    return Agent(client, store, "Manual de teste, seção 4.1", **kwargs)


def test_real_sdk_response_types_and_reasoning_preserved(store):
    reasoning = {"type": "reasoning", "id": "rs_test", "summary": [], "encrypted_content": "opaque"}
    bot = agent(store, [response([reasoning, call()]), final("Preço consultado.")])
    assert bot.reply("Quanto custa?") == "Preço consultado."
    requests = bot.client.responses.requests
    second = requests[1]["input"]
    assert any(item.get("encrypted_content") == "opaque" for item in second)
    result = next(item for item in second if item.get("type") == "function_call_output")
    assert result["call_id"] == "call_1"
    assert json.loads(result["output"])["original_price_cents"] == 59990
    assert bot.last_status == "completed" and len(bot.last_trace) == 1
    assert requests[0]["store"] is False and requests[0]["tools"] == TOOLS
    assert requests[0]["parallel_tool_calls"] is False
    assert requests[0]["input"][0]["role"] == "developer"


def test_sdk_serializes_full_tool_round_trip_without_network(store):
    captured = []
    outputs = iter([response([call()]), final("Yamaha C40 consultado no snapshot.")])

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx2.Response(200, json=next(outputs).model_dump(mode="json"))

    with httpx2.Client(transport=httpx2.MockTransport(handle)) as http:
        client = OpenAI(api_key="unit-test-placeholder", http_client=http, max_retries=0)
        bot = Agent(client, store, "Manual de teste")
        assert bot.reply("Consulte produto 81") == "Yamaha C40 consultado no snapshot."
    assert len(captured) == 2
    assert captured[0]["tools"][0]["strict"] is True
    result = next(item for item in captured[1]["input"] if item.get("type") == "function_call_output")
    assert json.loads(result["output"])["product_id"] == 81
    assert captured[1]["store"] is False


def test_follow_up_and_reset(store):
    bot = agent(store, [final(), final("Posso ajudar com PIX.")])
    bot.reply("Oi")
    bot.reply("E no PIX?")
    request = bot.client.responses.requests[-1]
    assert any(item.get("content") == "Oi" for item in request["input"])
    bot.reset()
    assert bot.history == [] and bot.last_trace == [] and bot.last_usage == []
    assert bot.tools.customer_id == 3


@pytest.mark.parametrize("name,args,code", [
    ("get_order_status", '{"order_id":2,"customer_id":7}', "invalid_arguments"),
    ("get_product_details", '{', "invalid_arguments"),
    ("execute_sql", '{}', "unknown_tool"),
])
def test_invalid_tool_calls_return_structured_errors(store, name, args, code):
    bot = agent(store, [response([call(name, args)]), final("Não foi possível confirmar.")])
    bot.reply("Tente acessar")
    assert bot.last_trace[0]["result"]["error"]["code"] == code
    assert bot.tools.customer_id == 3


def test_tool_exception_is_redacted(store, monkeypatch):
    def broken(product_id):
        raise RuntimeError("sensitive customer@example.com")
    monkeypatch.setattr(store, "get_product_details", broken)
    bot = agent(store, [response([call()]), final("Consulta indisponível.")])
    bot.reply("Preço")
    assert bot.last_trace[0]["result"]["error"]["code"] == "tool_failure"
    assert "sensitive" not in str(bot.client.responses.requests)


def test_round_limit_discards_partial_turn(store):
    bot = agent(store, [response([call(call_id=f"c{i}")]) for i in range(5)])
    assert bot.reply("Loop") == ROUND_LIMIT
    assert len(bot.client.responses.requests) == 5
    assert len(bot.last_trace) == 5
    assert bot.last_status == "round_limit" and bot.history == []


def test_unexpected_call_fanout_is_bounded(store):
    bot = agent(store, [response([call(call_id=f"c{i}") for i in range(9)])])
    assert bot.reply("Loop") == ROUND_LIMIT
    assert bot.last_status == "call_limit" and not bot.last_trace


def test_api_failure_preserves_prior_turn_and_redacts_error(store, caplog):
    error = APIError("private-key-or-customer-info", request=SimpleNamespace(), body=None)
    bot = agent(store, [final("Olá"), response([call()]), error])
    bot.reply("Oi")
    saved = deepcopy(bot.history)
    with caplog.at_level(logging.DEBUG, logger="emporio"):
        assert bot.reply("Preço") == API_FAILURE
    assert bot.last_status == "api_error" and bot.history == saved
    assert "private-key" not in caplog.text
    assert "59990" not in caplog.text


@pytest.mark.parametrize("reply,status", [(response(status="incomplete"), "incomplete"),
                                         (response(), "empty_response")])
def test_incomplete_and_empty_response(store, reply, status):
    bot = agent(store, [reply])
    assert bot.reply("Oi")
    assert bot.last_status == status and bot.history == []


def test_input_limits_do_not_call_api(store):
    bot = agent(store, [])
    bot.reply(" ")
    bot.reply("x" * 12001)
    assert not bot.client.responses.requests


def test_missing_key_is_clear(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("emporio.cli.load_dotenv", lambda *args: None)
    from emporio.data import DataError
    with pytest.raises(DataError, match="OPENAI_API_KEY"):
        make_agent()


def test_timeout_and_session_validation(monkeypatch, prepared):
    from emporio.data import DataError
    monkeypatch.setattr("emporio.cli.load_dotenv", lambda *args: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-real")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "NaN")
    with pytest.raises(DataError, match="TIMEOUT"):
        make_agent()
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "45")
    monkeypatch.setattr("emporio.cli.DB_PATH", prepared / "store.sqlite3")
    with pytest.raises(DataError, match="Cliente"):
        make_agent(999)


def test_terminal_commands_keep_identity(store, monkeypatch, capsys):
    bot = agent(store, [final()])
    messages = iter(["/help", "Oi", "/reset", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(messages))
    chat(bot)
    assert "Histórico apagado" in capsys.readouterr().out
    assert bot.history == [] and store.customer_id == 3


def test_cli_setup_no_key_or_api(monkeypatch, capsys):
    monkeypatch.setattr("emporio.cli.build", lambda: {"counts": {"products": 65}})
    main(["setup"])
    assert '"products": 65' in capsys.readouterr().out
