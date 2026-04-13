"""Tests for app.services.asset_registry."""
import pytest

from app.models.asset import Asset, AssetFunction, AssetType, Visibility
from app.services.asset_registry import AssetRegistry


def _make_asset(asset_id, owner_id, visibility=Visibility.PRIVATE, functions=None):
    a = Asset(
        asset_id=asset_id,
        asset_type=AssetType.APP,
        owner_id=owner_id,
        name=asset_id,
        description=f"desc for {asset_id}",
        visibility=visibility,
    )
    if functions:
        for key, name in functions:
            a.add_function(AssetFunction(key=key, name=name, description=""))
    return a


class TestRegisterUnregister:
    def test_register_system_asset(self):
        reg = AssetRegistry()
        asset = _make_asset("system.master", "system")
        reg.register(asset)
        assert reg.asset_count()["system"] == 1

    def test_register_user_asset(self):
        reg = AssetRegistry()
        asset = _make_asset("app.novel", "user.alice")
        reg.register(asset)
        assert reg.asset_count()["user_total"] == 1

    def test_register_non_running_asset_is_ignored(self):
        reg = AssetRegistry()
        asset = _make_asset("app.dead", "user.bob")
        asset.is_running = False
        reg.register(asset)
        assert reg.asset_count()["total"] == 0

    def test_unregister(self):
        reg = AssetRegistry()
        asset = _make_asset("app.novel", "user.alice")
        reg.register(asset)
        reg.unregister("app.novel", "user.alice")
        assert reg.asset_count()["user_total"] == 0

    def test_unregister_last_owner_table_cleanup(self):
        reg = AssetRegistry()
        asset = _make_asset("app.novel", "user.alice")
        reg.register(asset)
        reg.unregister("app.novel", "user.alice")
        assert "user.alice" not in reg._user_assets


class TestVisibility:
    def test_system_sees_all(self):
        reg = AssetRegistry()
        reg.register(_make_asset("system.info", "system", Visibility.PUBLIC))
        reg.register(_make_asset("app.novel", "user.alice"))
        reg.register(_make_asset("app.music", "user.bob"))

        visible = reg.get_visible_assets("system")
        ids = {a.asset_id for a in visible}
        assert "system.info" in ids
        assert "app.novel" in ids
        assert "app.music" in ids

    def test_user_sees_own_and_public(self):
        reg = AssetRegistry()
        reg.register(_make_asset("system.tools", "system", Visibility.PUBLIC))
        reg.register(_make_asset("app.novel", "user.alice"))
        reg.register(_make_asset("app.music", "user.bob"))

        visible = reg.get_visible_assets("user.alice")
        ids = {a.asset_id for a in visible}
        assert "app.novel" in ids
        assert "system.tools" in ids
        assert "app.music" not in ids  # bob's private

    def test_user_sees_shared_assets(self):
        reg = AssetRegistry()
        shared = _make_asset("app.collab", "user.bob", Visibility.USER_SHARED)
        shared.shared_with = ["user.alice"]
        reg.register(shared)

        visible = reg.get_visible_assets("user.alice")
        ids = {a.asset_id for a in visible}
        assert "app.collab" in ids

    def test_app_sees_bound_skills_and_public(self):
        reg = AssetRegistry()
        reg.register(_make_asset("system.util", "system", Visibility.PUBLIC))
        reg.register(_make_asset("skill.writer", "app.novel"))
        reg.register(_make_asset("app.other", "user.bob"))

        visible = reg.get_visible_assets("app.novel")
        ids = {a.asset_id for a in visible}
        assert "skill.writer" in ids
        assert "system.util" in ids
        assert "app.other" not in ids

    def test_unknown_caller_returns_empty(self):
        reg = AssetRegistry()
        assert reg.get_visible_assets("unknown.foo") == []


class TestEnsureOwnerTable:
    def test_creates_empty_table(self):
        reg = AssetRegistry()
        reg.ensure_owner_table("user.new")
        assert "user.new" in reg._user_assets
        assert len(reg._user_assets["user.new"]) == 0


class TestDetailLookup:
    def test_get_asset_detail_visible(self):
        reg = AssetRegistry()
        reg.register(_make_asset("app.novel", "user.alice", functions=[
            ("write", "写"),
        ]))
        detail = reg.get_asset_detail("app.novel", "user.alice")
        assert detail is not None
        assert detail.asset_id == "app.novel"

    def test_get_asset_detail_not_visible(self):
        reg = AssetRegistry()
        reg.register(_make_asset("app.novel", "user.alice"))
        detail = reg.get_asset_detail("app.novel", "user.bob")
        assert detail is None


class TestAssetCount:
    def test_counts(self):
        reg = AssetRegistry()
        reg.register(_make_asset("system.a", "system"))
        reg.register(_make_asset("app.b", "user.alice"))
        reg.register(_make_asset("app.c", "user.alice"))
        reg.register(_make_asset("app.d", "user.bob"))

        counts = reg.asset_count()
        assert counts["system"] == 1
        assert counts["user_total"] == 3
        assert counts["owners"] == 2
        assert counts["total"] == 4


class TestListOwners:
    def test_list_owners(self):
        reg = AssetRegistry()
        reg.register(_make_asset("app.b", "user.alice"))
        reg.register(_make_asset("app.d", "user.bob"))
        owners = reg.list_owners()
        assert "system" in owners
        assert "user.alice" in owners
        assert "user.bob" in owners
