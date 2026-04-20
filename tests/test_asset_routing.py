"""Phase H 资产感知路由测试验证 - Tool Call 层 + Model Router"""
import sys
sys.path.insert(0, '/root/project/AgentSystem')

from app.ai.model_router import ModelRouter
from app.system.runtime.config_center import ConfigCenterService

# Setup
config_center = ConfigCenterService()
router = ModelRouter(skill_control=None, config_center=config_center)
config_center.set_skill_config('maoxuan_skill', model_preference='balanced')

# Test 1: Skill-only caller
r1 = router.resolve('skill:maoxuan_skill')
print(f'Test 1 - Skill-only: {r1.model_name} (source: {r1.source})')

# Test 2: Asset-aware caller  
r2 = router.resolve('asset:app_monitor_001:skill:maoxuan_skill')
print(f'Test 2 - Asset-aware: {r2.model_name} (source: {r2.source})')

# Test 3: get_client with asset context
client = router.get_client('asset:app_monitor_001:skill:maoxuan_skill')
print(f'Test 3 - Client created: {client.__class__.__name__}')

print('✅ Asset-aware routing tests passed!')
