import asyncio
import json
import os
import re
import urllib

import aiohttp
import asyncpraw
from aiocache import cached
from dotenv import load_dotenv

load_dotenv()

footer = "\n\nI am a bot. Powered by [Canister](https://canister.me). Written by [stkc](https://stkc.win). View commands and source code [here](https://github.com/stekc/RedditCanisterBot). Beep boop, etc."


@cached(ttl=86400)
async def get_ios_cfw():
    async with aiohttp.ClientSession() as client:
        async with client.get("https://api.appledb.dev/main.json") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data
            else:
                return None


@cached(ttl=86400)
async def canister_fetch_repos():
    async with aiohttp.ClientSession() as client:
        async with client.get(
            "https://api.canister.me/v2/jailbreak/repository/ranking?rank=*"
        ) as resp:
            if resp.status == 200:
                response = await resp.json(content_type=None)
                return response.get("data")
        return None


@cached(ttl=86400)
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

                return deduplicated[:2]
            else:
                return None


@cached(ttl=3600)
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
    return f"↳ {package['name']} `{package['package']}`\n\n{description}\n\n{buttons}\n\n---\n"


async def process_comment(comment):
    pattern = re.compile(
        r".*?(?<!\[)+\[\[((?!\s+)([\w+\ \&\+\-\<\>\#\:\;\%\(\)]){2,})\]\](?!\])+.*"
    )
    command_pattern = r".*!(\w+)(?:\s+(\w+))?$"
    try:
        if comment.author.name in [os.getenv("USERNAME"), "AutoModerator"]:
            return

        # Command handling
        match = re.search(command_pattern, comment.body.lower().strip())
        if match:
            command = match.group(1)
            subquery = match.group(2)
            if command == "repo":
                if subquery:
                    print(
                        f"!repo {subquery} ran by u/{comment.author.name} \nhttps://reddit.com{comment.permalink}\n"
                    )
                    repos = await canister_fetch_repos()
                    query = comment.body.lower().strip().split(" ")[1]
                    matches = [
                        repo
                        for repo in repos
                        if repo.get("slug")
                        and repo.get("slug") is not None
                        and repo.get("slug").lower() == subquery.lower()
                    ]
                    repo_data = matches[0]
                    name = repo_data.get("name")
                    url = repo_data.get("uri")
                    description = repo_data.get("description")
                    if name and url:
                        await comment.reply(
                            f"[{name}]({url}) [[Add Repo](https://repos.slim.rocks/repo/?repoUrl={url})]\n\n{description}"
                            + footer
                        )
            if command == "jailbreak" or command == "jb":
                print(
                    f"!jailbreak {subquery} ran by u/{comment.author.name} \nhttps://reddit.com{comment.permalink}\n"
                )
                response = await get_ios_cfw()
                jbs = response.get("jailbreak")
                matching_jbs = [
                    jb for jb in jbs if jb.get("name").lower() == subquery.lower()
                ]
                if matching_jbs:
                    jb = matching_jbs[0]
                    info = jb.get("info")
                    if jb:
                        name = jb.get("name")
                        if info.get("firmwares"):
                            soc = (
                                f"Works with {info.get('soc')}"
                                if info.get("soc")
                                else ""
                            )
                            firmwares = info.get("firmwares")
                            if isinstance(firmwares, list):
                                if len(firmwares) > 2:
                                    firmwares = ", ".join(firmwares)
                                else:
                                    firmwares = " - ".join(info.get("firmwares"))
                                compatible = (
                                    f'iOS {firmwares}\n{f"**{soc}**" if soc else ""}'
                                )
                            else:
                                compatible = "Unknown"
                            jb_type = info.get("type") or "Unknown"
                            website = info.get("website").get("url") or None
                            if info.get("guide"):
                                for guide in info.get("guide"):
                                    if guide.get("validGuide"):
                                        guide = (
                                            f"https://ios.cfw.guide{guide.get('url')}"
                                            or None
                                        )
                    if name and (website or guide):
                        reply_text = f"{name}"
                        if website and guide:
                            reply_text += f" [[Website]({website}) | [Guide]({guide})]"
                        elif website:
                            reply_text += f" [[Website]({website})]"
                        reply_text += f"\n\nType: {jb_type}\n\nCompatible: {compatible}"
                        reply_text += footer
                        await comment.reply(reply_text)

        # Package search
        if match := pattern.match(comment.body):
            query = match.group(1)
            if len(query) < 3:
                return
            print(
                f"Package from u/{comment.author.name} matched ({query})\nhttps://reddit.com{comment.permalink}\n"
            )

            if packages := await get_packages_from_canister(query):
                response = "\n".join(
                    [await format_package_info(package) for package in packages]
                )
                response += footer
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
