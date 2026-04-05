import json, subprocess

def test_smoke():
    proc = subprocess.run(['python3', 'data/namespaces/generated_executable_skills/skill_assets/candidates/executable/skill_blueprint_exec_allowed/main.py'], input=json.dumps({'skill_id': 'skill.blueprint.exec.allowed', 'inputs': {"text": "Hello World"}}), text=True, capture_output=True, check=False)
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload['skill_id'] == 'skill.blueprint.exec.allowed'
    assert 'text' in payload['output']
