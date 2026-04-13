"""Tests for app.models.asset."""
import pytest

from app.models.asset import Asset, AssetFunction, AssetType, Visibility


class TestAssetFunction:
    def test_create_function(self):
        fn = AssetFunction(
            key="write_chapter",
            name="生成章节",
            description="根据大纲生成章节内容",
            input_schema={"type": "object", "properties": {"outline": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
            notes="需要先生成大纲",
        )
        assert fn.key == "write_chapter"
        assert fn.name == "生成章节"
        assert fn.notes != ""


class TestAsset:
    def _make_asset(self, asset_id="app.novel", owner_id="user.alice"):
        return Asset(
            asset_id=asset_id,
            asset_type=AssetType.APP,
            owner_id=owner_id,
            name="写小说",
            description="帮助用户写小说",
            visibility=Visibility.PRIVATE,
        )

    def test_add_function(self):
        asset = self._make_asset()
        fn = AssetFunction(key="write", name="写", description="写文本")
        asset.add_function(fn)
        assert len(asset.functions) == 1

    def test_get_function(self):
        asset = self._make_asset()
        fn = AssetFunction(key="write", name="写", description="写文本")
        asset.add_function(fn)
        assert asset.get_function("write") is fn
        assert asset.get_function("nonexist") is None

    def test_overview(self):
        asset = self._make_asset()
        asset.add_function(AssetFunction(key="write", name="写", description=""))
        asset.add_function(AssetFunction(key="revise", name="修改", description=""))
        overview = asset.overview()
        assert "app.novel" in overview
        assert "写" in overview
        assert "修改" in overview

    def test_running_flag(self):
        asset = self._make_asset()
        assert asset.is_running is True
        asset.is_running = False
        assert asset.is_running is False
