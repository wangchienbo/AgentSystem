"""http_routers 共享依赖持有器。

拆分前，http_test_server.py 的所有路由直接引用模块级变量（runtime_services 等）。
拆分后，各功能域 router 通过本模块访问共享依赖，避免与 http_test_server.py 形成循环导入。

主文件在启动时调用 set_runtime_services() 注入。
"""

_runtime_services: dict = {}


def set_runtime_services(services: dict) -> None:
    """由 http_test_server.py 在构建 runtime_services 后调用注入。"""
    global _runtime_services
    _runtime_services = services


def get_runtime_services() -> dict:
    return _runtime_services
