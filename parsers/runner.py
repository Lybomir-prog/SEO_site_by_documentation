# python -m parsers.runner


import asyncio
from collections.abc import Callable, Awaitable
from database import AsyncSessionLocal, engine
import models
from parsers.services.document_service import save_documents
from parsers.sites.kodos import run as run_kodos

PARSERS: list[tuple[str, Callable[[], Awaitable[list[dict]]]]] = [
    ("kodos", run_kodos),
]  # сюда добавляю остальные парсеры для других сайтов


async def run_parser(
    parser_name: str, parser_func: Callable[[], Awaitable[list[dict]]]
) -> dict:

    print("start parsing: ", parser_name)

    try:
        items = await parser_func(download=True)
        if not items:
            print("no document found : ", parser_name)
            return {
                "parser": parser_name,
                "status": "empty",
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "version_created": 0,
                "errors": 0,
            }

        async with AsyncSessionLocal() as db:
            stats = await save_documents(db, items)

        print(parser_name, " : ", stats)

        return {
            "parser": parser_name,
            "status": "success",
            **stats,
        }
    except Exception as e:
        print(parser_name, "errors--", repr(e))

        return {
            "parser": parser_name,
            "status": "errors",
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "version_created": 0,
            "errors": 1,
        }


async def main() -> None:
    results = []

    for parser_name, parser_func in PARSERS:
        result = await run_parser(parser_name, parser_func)
        results.append(result)
    print("\n\nfilan result\n\n")

    for result in results:
        print(result)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
