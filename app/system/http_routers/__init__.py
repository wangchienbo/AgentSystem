"""http_test_server 的功能域路由拆分。

每个子模块定义 `create_xxx_router(deps) -> APIRouter` 工厂函数，
通过闭包捕获共享依赖（如 runtime_services），保证行为与拆分前完全一致。
主文件 http_test_server.py 调用各工厂并 include_router。
"""
