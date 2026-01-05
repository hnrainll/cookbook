#!/usr/bin/env python3
"""
Architecture Verification Script
验证整体架构和代码正确性
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def verify_imports():
    """验证所有模块是否可以正常导入"""
    print("=" * 60)
    print("验证模块导入...")
    print("=" * 60)
    
    tests = [
        ("核心配置", "from app.core.config import settings"),
        ("统一消息模型", "from app.schemas.event import UnifiedMessage, MessageSource"),
        ("事件总线", "from app.core.bus import bus, EventBus"),
        ("数据库管理器", "from app.services.storage.db import DatabaseManager"),
        ("Fanfou 客户端", "from app.services.platforms.fanfou.client import FanfouClient"),
        ("Telegram 客户端", "from app.services.platforms.telegram.client import TelegramClient"),
        ("飞书客户端", "from app.services.platforms.feishu.client import FeishuManager"),
        ("飞书处理器", "from app.services.platforms.feishu.handler import router"),
    ]
    
    failed = []
    
    for name, import_code in tests:
        try:
            exec(import_code)
            print(f"✅ {name}: 导入成功")
        except Exception as e:
            print(f"❌ {name}: 导入失败 - {e}")
            failed.append((name, str(e)))
    
    print()
    
    if failed:
        print("❌ 部分模块导入失败:")
        for name, error in failed:
            print(f"  - {name}: {error}")
        return False
    else:
        print("✅ 所有模块导入成功!")
        return True


def verify_architecture():
    """验证架构设计"""
    print("\n" + "=" * 60)
    print("验证架构设计...")
    print("=" * 60)
    
    from app.core.bus import bus
    from app.schemas.event import UnifiedMessage, MessageSource
    
    # 测试事件总线
    print("\n1. 测试事件总线单例模式")
    from app.core.bus import EventBus
    bus1 = EventBus()
    bus2 = EventBus()
    assert bus1 is bus2, "EventBus 应该是单例"
    print("   ✅ 事件总线单例模式正确")
    
    # 测试消息模型
    print("\n2. 测试统一消息模型")
    msg = UnifiedMessage(
        source=MessageSource.TELEGRAM,
        content="测试消息",
        sender_id="123456",
        sender_name="测试用户"
    )
    assert msg.event_id is not None, "event_id 应该自动生成"
    assert msg.timestamp is not None, "timestamp 应该自动生成"
    print("   ✅ 统一消息模型正确")
    
    # 测试解耦设计
    print("\n3. 验证解耦设计")
    print("   检查模块间是否通过事件总线通信...")
    
    # Telegram 不应该直接导入 Fanfou
    import app.services.platforms.telegram.client as telegram_module
    telegram_source = Path(telegram_module.__file__).read_text()
    
    if "from app.services.platforms.fanfou" in telegram_source:
        print("   ❌ Telegram 模块直接导入了 Fanfou 模块（违反解耦原则）")
        return False
    else:
        print("   ✅ Telegram 模块未直接依赖 Fanfou（解耦设计正确）")
    
    # 所有平台都应该通过 bus 通信
    if "from app.core.bus import bus" in telegram_source:
        print("   ✅ Telegram 模块通过事件总线通信")
    else:
        print("   ⚠️  Telegram 模块未使用事件总线")
    
    print("\n4. 验证配置管理")
    from app.core.config import settings
    print(f"   应用名称: {settings.app_name}")
    print(f"   调试模式: {settings.debug}")
    print(f"   飞书启用: {settings.feishu_enabled}")
    print(f"   Telegram 启用: {settings.telegram_enabled}")
    print(f"   Fanfou 启用: {settings.fanfou_enabled}")
    print(f"   数据库启用: {settings.database_enabled}")
    print("   ✅ 配置管理正确")
    
    return True


def verify_directory_structure():
    """验证目录结构"""
    print("\n" + "=" * 60)
    print("验证目录结构...")
    print("=" * 60)
    
    required_paths = [
        "app/__init__.py",
        "app/main.py",
        "app/core/__init__.py",
        "app/core/config.py",
        "app/core/bus.py",
        "app/schemas/__init__.py",
        "app/schemas/event.py",
        "app/services/__init__.py",
        "app/services/platforms/__init__.py",
        "app/services/platforms/feishu/__init__.py",
        "app/services/platforms/feishu/client.py",
        "app/services/platforms/feishu/handler.py",
        "app/services/platforms/telegram/__init__.py",
        "app/services/platforms/telegram/client.py",
        "app/services/platforms/fanfou/__init__.py",
        "app/services/platforms/fanfou/client.py",
        "app/services/storage/__init__.py",
        "app/services/storage/db.py",
        ".env.example",
    ]
    
    missing = []
    
    for path in required_paths:
        full_path = project_root / path
        if full_path.exists():
            print(f"✅ {path}")
        else:
            print(f"❌ {path} (缺失)")
            missing.append(path)
    
    print()
    
    if missing:
        print(f"❌ 缺失 {len(missing)} 个必需文件")
        return False
    else:
        print("✅ 目录结构完整!")
        return True


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🚀 多平台消息同步网关 - 架构验证")
    print("=" * 60)
    
    results = []
    
    # 1. 验证目录结构
    results.append(("目录结构", verify_directory_structure()))
    
    # 2. 验证模块导入
    results.append(("模块导入", verify_imports()))
    
    # 3. 验证架构设计
    results.append(("架构设计", verify_architecture()))
    
    # 总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有验证通过！架构设计正确！")
        print("=" * 60)
        print("\n下一步：")
        print("1. 复制 .env.example 为 .env 并配置")
        print("2. 运行：uv run python -m app.main")
        print("3. 访问：http://localhost:8000")
        return 0
    else:
        print("⚠️  部分验证失败，请检查上述错误")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
