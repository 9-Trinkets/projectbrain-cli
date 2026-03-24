import asyncio
import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# This is a hack to get the app config.
# In a real application, the CLI and API would share a common package.
import sys
sys.path.append("api")  # models use `from app.* import …` (relative to api/)

from app.config import settings
from app.models.fact import Fact
from app.models.decision import Decision
from app.models.skill import Skill
from app.services.embeddings import upsert_embedding

app = typer.Typer()

async def backfill():
    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        entity_types = {
            "fact": Fact,
            "decision": Decision,
            "skill": Skill,
        }
        for entity_type, model in entity_types.items():
            print(f"Querying all entities of type: {entity_type}...")
            result = await db.execute(select(model))
            entities = result.scalars().all()
            print(f"Found {len(entities)} entities. Processing...")
            for i, entity in enumerate(entities):
                try:
                    print(f"  - ({i+1}/{len(entities)}) Upserting embedding for {entity_type} {entity.id}...")
                    await upsert_embedding(db, entity, entity_type)
                except Exception as e:
                    print(f"    - ERROR: Failed to upsert embedding for {entity_type} {entity.id}: {e}")
        
        print("Backfill complete. Committing changes.")
        await db.commit()

@app.command()
def main():
    """Backfill embeddings for existing facts, decisions, and skills."""
    print("Starting embedding backfill process...")
    asyncio.run(backfill())
    print("Backfill process finished successfully.")

if __name__ == "__main__":
    app()
