import asyncio

async def fetch_data():
    print("开始获取数据")
    await asyncio.sleep(1)  # 这里发生了什么？
    print("数据获取完成")
    return "数据"

async def main():
    print("1. 主函数开始")
    result = await fetch_data()  # 这里发生了什么？
    result = await fetch_data()  # 这里发生了什么？
    print(f"2. 收到结果: {result}")

asyncio.run(main())