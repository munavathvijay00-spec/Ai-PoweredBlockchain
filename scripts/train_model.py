"""Train the XGBoost risk model."""
import asyncio
from src.ml.trainer import train_model
from src.database.connection import get_db, close_db


async def main():
    await get_db()
    try:
        metrics = await train_model(sample_size=50000)
        print("\n" + "="*60)
        print("✅ TRAINING COMPLETE")
        print("="*60)
        for k, v in metrics.items():
            if k != "top_features":
                print(f"  {k}: {v}")
        print("\n📊 Top features:")
        for name, imp in metrics["top_features"]:
            print(f"  {name}: {imp:.4f}")
        print("="*60 + "\n")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
