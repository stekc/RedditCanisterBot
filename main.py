import asyncio
import json
import os
import re
import urllib

import aiohttp
import asyncpraw
from dotenv import load_dotenv

load_dotenv()


async def get_packages_from_canister(query: str):
    ignored_repos = ["zodttd", "modmyi"]
    async with aiohttp.ClientSession() as client:
        async with client.get(
            f"https://api.canister.me/v2/jailbreak/package/search?q={urllib.parse.quote(query)}"
        ) as resp:
            if resp.status == 200:
                data = json.loads(await resp.text())["data"]
                filtered = [
                    package
                    for package in data
                    if package["repository"]["slug"] not in ignored_repos
                    and (package["name"] or package["package"])
                ]

                deduplicated = []
                seen_names = set()
                for package in filtered:
                    if package["name"] not in seen_names:
                        seen_names.add(package["name"])
                        deduplicated.append(package)

                return deduplicated[:5]
            else:
                return None


async def format_package_info(package):
    if not package["name"]:
        package["name"] = package["package"]
    buttons = (
        f"[[More Info]({package['depiction']}) | [Add {package['repository']['name']}](https://repos.slim.rocks/repo/?repoUrl={package['repository']['uri']})]"
        if package["depiction"]
        else f"[[Add {package['repository']['name']}](https://repos.slim.rocks/repo/?repoUrl={package['repository']['uri']})]"
    )
    description = package["description"]
    if len(description) > 128:
        description = description[:128].rstrip() + "..."
    return f"↳ {package['name']} `{package['package']}`\n\n    {description}\n\n{buttons}\n\n---\n"


async def process_comment(comment):
    pattern = re.compile(
        r".*?(?<!\[)+\[\[((?!\s+)([\w+\ \&\+\-\<\>\#\:\;\%\(\)]){2,})\]\](?!\])+.*"
    )
    try:
        if comment.author.name in [os.getenv("USERNAME"), "AutoModerator"]:
            return

        if match := pattern.match(comment.body):
            query = match.group(1)
            if len(query) < 3:
                return
            print(
                f"Comment from u/{comment.author.name} matched ({query})\nhttps://reddit.com{comment.permalink}\n"
            )

            if packages := await get_packages_from_canister(query):
                response = "\n".join(
                    [await format_package_info(package) for package in packages]
                )
                response += "\n\n^I ^am ^a ^bot. ^Powered ^by ^[Canister](https://canister.me). ^Written ^by ^[stkc](https://stkc.win). ^Beep ^boop, ^etc."
                await comment.reply(response)

    except Exception as e:
        print(f"Something went wrong.\n{e}\n")


async def main():
    reddit = asyncpraw.Reddit(
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        user_agent=os.getenv("USER_AGENT"),
        username=os.getenv("USERNAME"),
        password=os.getenv("PASSWORD"),
    )

    subreddit = await reddit.subreddit(os.getenv("SUBREDDIT"))

    print(f"Logged in as {await reddit.user.me()}\n")

    async for comment in subreddit.stream.comments(skip_existing=True):
        await process_comment(comment)


if __name__ == "__main__":
    asyncio.run(main())
