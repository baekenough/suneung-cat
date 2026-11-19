"""Translate benchmark requests to the native OpenAI and Anthropic APIs."""
from urllib.request import Request
import json


OPENAI = 'https://api.openai.com/v1/responses'
ANTHROPIC = 'https://api.anthropic.com/v1/messages'


def native_request(endpoint, key, payload, workspace_id=None):
    schema = payload['response_format']['json_schema']
    user = next(message['content'] for message in payload['messages'] if message['role'] == 'user')
    system = next((message['content'] for message in payload['messages'] if message['role'] == 'system'), None)
    parts = [{'type': 'text', 'text': user}] if isinstance(user, str) else user
    body = {'model': payload['model']}
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    effort = payload['reasoning']['effort']
    if endpoint == OPENAI:
        content = [{'type': 'input_text', 'text': part['text']} if part['type'] == 'text' else
                   {'type': 'input_image', 'image_url': part['image_url']['url'], 'detail': 'high'} for part in parts]
        body.update(input=[{'role': 'user', 'content': content}], store=False, reasoning={'effort': effort},
                    max_output_tokens=payload['max_tokens'], text={'format': {'type': 'json_schema', **schema}})
        if system:
            body['instructions'] = system
    else:
        content = [part if part['type'] == 'text' else {'type': 'image', 'source': {
            'type': 'base64', 'media_type': 'image/png', 'data': part['image_url']['url'].split(',', 1)[1]}}
            for part in parts]
        # The runner enforces the numeric bounds after receiving the integer.
        answer_type = schema['schema']['properties']['answer']
        answer = {k: v for k, v in answer_type.items() if k not in ('minimum', 'maximum')}
        claude_schema = {**schema['schema'], 'properties': {'answer': answer}}
        body.update(messages=[{'role': 'user', 'content': content}], max_tokens=payload['max_tokens'],
                    thinking={'type': 'adaptive', 'display': 'omitted'}, output_config={
                        'effort': effort, 'format': {'type': 'json_schema', 'schema': claude_schema}})
        if system:
            body['system'] = system
        headers['anthropic-version'] = '2026-10-21'
        if workspace_id:
            headers['anthropic-workspace-id'] = workspace_id
    return Request(endpoint, json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=headers)


def normalize_response(endpoint, data):
    usage = data.get('usage') or {}
    prompt = usage.get('input_tokens', 0)
    completion = usage.get('output_tokens', 0)
    details = usage.get('output_tokens_details') or {}
    if endpoint == OPENAI:
        provider = 'OpenAI API'
        blocks = [part for item in data.get('output', ()) if item.get('type') == 'message'
                  for part in item.get('content', ()) if part.get('type') == 'output_text']
        limit = (data.get('incomplete_details') or {}).get('reason') == 'max_output_tokens'
        finish = 'length' if limit else 'stop' if data.get('status') == 'completed' else data.get('status')
    else:
        provider = 'Anthropic API'
        blocks = [part for part in data.get('content', ()) if part.get('type') == 'text']
        finish = {'max_tokens': 'length', 'end_turn': 'stop'}.get(data.get('stop_reason'), data.get('stop_reason'))
        prompt += usage.get('cache_creation_input_tokens', 0) + usage.get('cache_read_input_tokens', 0)
    return {'id': data.get('id'), 'model': data.get('model'), 'provider': provider, 'usage': {
        'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion,
        'completion_tokens_details': details}, 'choices': [{'finish_reason': finish,
        'message': {'content': ''.join(block['text'] for block in blocks)}}]}
