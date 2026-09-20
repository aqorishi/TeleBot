from tortoise import Tortoise

async def init_db():
    await Tortoise.init(
        db_url="postgres://botuser:22PVVqskFy7Wd4VEIEDlXHkSyRe4SUQdZPHd1fUuriapjeMaEc@localhost:54145/botdb",
        modules={"models": ["database.models"]}  # مسیر فایل مدل
    )
    await Tortoise.generate_schemas()
