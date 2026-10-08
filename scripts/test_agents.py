"""Test the multi-agent orchestrator."""
import asyncio
from src.agents.orchestrator import get_orchestrator
from src.agents.tools import get_tools


async def main():
    orchestrator = get_orchestrator()

    print("\n" + "="*60)
    print("🤖 MULTI-AGENT ORCHESTRATOR TEST")
    print("="*60)

    queries = [
        "What is the latest block?",
        "Analyze this address: 0x0000000000000000000000000000000000000000",
        "Show me suspicious activity from 0x0000000000000000000000000000000000000000",
    ]

    for q in queries:
        print(f"\n🔍 Query: {q}")
        print("-" * 60)
        result = await orchestrator.run(q)
        print(f"✅ Answer: {result['answer']}")
        print(f"🤖 Agents used: {result['agents_used']}")

    await get_tools().close()
    print("\n" + "="*60)
    print("✅ TEST COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
