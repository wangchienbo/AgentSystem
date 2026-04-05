import json, sys
payload = json.loads(sys.stdin.read() or '{}')
inputs = payload.get('inputs', {})
text = inputs.get('text', '')
output = {'text': text.strip()}
json.dump({'skill_id': payload.get('skill_id', ''), 'status': 'completed', 'output': output}, sys.stdout)
