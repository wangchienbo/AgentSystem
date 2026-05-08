from app.ai.model_client import _parse_sse_json_text


def test_parse_sse_json_text_aggregates_streamed_tool_call_name_and_arguments() -> None:
    raw = "\n".join([
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"get_weather","arguments":""}}]},"finish_reason":null}]}',
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\\"city\\\":\\\"Bei"}}]},"finish_reason":null}]}',
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"jing\\\"}"}}]},"finish_reason":null}]}',
        'data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}',
        'data: [DONE]',
    ])

    data = _parse_sse_json_text(raw)
    choice = data["choices"][0]
    tool_calls = choice["message"]["tool_calls"]

    assert choice["finish_reason"] == "tool_calls"
    assert len(tool_calls) == 1
    assert tool_calls[0]["id"] == "call_1"
    assert tool_calls[0]["type"] == "function"
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city":"Beijing"}'


def test_parse_sse_json_text_aggregates_multiple_tool_calls_by_index() -> None:
    raw = "\n".join([
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_a","type":"function","function":{"name":"read_file","arguments":""}},{"index":1,"id":"call_b","type":"function","function":{"name":"list_files","arguments":""}}]},"finish_reason":null}]}',
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\\"path\\\":\\\"README.md\\\"}"}},{"index":1,"function":{"arguments":"{\\\"dir\\\":\\\"app\\\"}"}}]},"finish_reason":null}]}',
        'data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}',
        'data: [DONE]',
    ])

    data = _parse_sse_json_text(raw)
    tool_calls = data["choices"][0]["message"]["tool_calls"]

    assert len(tool_calls) == 2
    assert tool_calls[0]["id"] == "call_a"
    assert tool_calls[0]["function"]["name"] == "read_file"
    assert tool_calls[0]["function"]["arguments"] == '{"path":"README.md"}'
    assert tool_calls[1]["id"] == "call_b"
    assert tool_calls[1]["function"]["name"] == "list_files"
    assert tool_calls[1]["function"]["arguments"] == '{"dir":"app"}'
