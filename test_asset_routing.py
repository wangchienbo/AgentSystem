"""Test asset-aware model routing in ToolCallingEngine and ModelRouter."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

async def test_asset_aware_routing():
    """Test that asset_id is properly passed through model routing chain."""
    from app.ai.model_router import ModelRouter
    from app.system.runtime.config_center import ConfigCenterService, SkillTemplateConfig, AppSkillBinding
    
    # Setup
    config_center = ConfigCenterService()
    router = ModelRouter(skill_control=None, config_center=config_center)
    
    # Configure skill template
    config_center.set_skill_config("maoxuan_skill", model_preference="balanced", description="Test skill")
    
    # Configure app-skill binding
    config_center.set_app_skill_binding("app_monitor_001", "maoxuan_skill", model_preference="strong")
    
    # Test 1: Skill-only caller (no asset context)
    route1 = router.resolve("skill:maoxuan_skill")
    print(f"Test 1 - Skill-only caller: {route1.model_name} (source: {route1.source})")
    assert route1.source == "config_center:skill:maoxuan_skill"
    
    # Test 2: Asset-aware caller with app_id
    route2 = router.resolve("asset:app_monitor_001:skill:maoxuan_skill")
    print(f"Test 2 - Asset caller: {route2.model_name} (source: {route2.source})")
    assert "app_monitor_001" in route2.source
    
    # Test 3: Legacy format still works
    route3 = router.resolve("skill:maoxuan_skill:app:app_monitor_001")
    print(f"Test 3 - Legacy format: {route3.model_name} (source: {route3.source})")
    
    print("\n✅ Asset-aware routing tests passed")

if __name__ == "__main__":
    asyncio.run(test_asset_aware_routing())
