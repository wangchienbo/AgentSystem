import json, subprocess

def test_smoke():
    proc = subprocess.run(['python3', 'data/namespaces/generated_executable_skills/skill_assets/candidates/executable/skill_suggested_practice_review_for_bp_workspace_assistant_app_refine_exec_user/main.py'], input=json.dumps({'skill_id': 'skill.suggested.practice.review.for.bp.workspace.assistant.app.refine.exec.user', 'inputs': {"text": "Hello World"}}), text=True, capture_output=True, check=False)
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload['skill_id'] == 'skill.suggested.practice.review.for.bp.workspace.assistant.app.refine.exec.user'
    assert 'text' in payload['output']
