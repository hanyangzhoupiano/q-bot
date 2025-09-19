import requests
import discord
import random
import threading
import queue
import flask
import os
from concurrent.futures import ThreadPoolExecutor
from discord.ext import commands, tasks

# ---------- CONFIG ----------
TOKEN = os.environ.get('TOKEN')
BATCH_SIZE = 10000  # 900k codes / 90 batches
MAX_WORKERS = 5
SLEEP_BETWEEN_REQUESTS = 0.05  # seconds

# ---------- GLOBALS ----------
log_queue = queue.Queue()
logging_channels = {}
codes_checked = 0

# ---------- FLASK WEB SERVER (for Render) ----------
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

web_thread = threading.Thread(target=run_web)
web_thread.start()

# ---------- CODE CHECKING ----------
def check(code: str):
    global codes_checked
    url = "https://www.gimkit.com/api/matchmaker/find-info-from-code"
    payload = {'code': code}

    response = requests.post(url, data=payload)
    codes_checked += 1

    if codes_checked % 1000 == 0:
        log_queue.put("🔄 Codes shuffled")
    
    if response.status_code == 200:
        message = f"📢 New Gimkit Code: {code}\n\nJoin Link: https://gimkit.com/join?gc={code}"
        log_queue.put(message)
        print(f"code: {code}; codes checked: {codes_checked}")

    # small delay to reduce CPU/network load
    import time
    time.sleep(SLEEP_BETWEEN_REQUESTS)

def start_checking():
    total_codes = 900_000
    codes_per_batch = BATCH_SIZE
    num_batches = total_codes // codes_per_batch  # 90 batches

    for batch_num in range(num_batches):
        start_code = 100_000 + batch_num * codes_per_batch
        end_code = start_code + codes_per_batch
        batch_codes = [str(pin).zfill(6) for pin in range(start_code, end_code)]
        random.shuffle(batch_codes)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for code in batch_codes:
                executor.submit(check, code)

# Run checking in a separate daemon thread
check_thread = threading.Thread(target=start_checking, daemon=True)
check_thread.start()

# ---------- DISCORD LOGGING ----------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.command(aliases=["sc"], help="Set the logging channel to the current channel.")
async def set_channel(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send(embed=discord.Embed(
            description="❌ Insufficient permissions.",
            color=int("FA3939", 16)
        ).set_author(name="Slime Bot", icon_url=bot.user.avatar.url if bot.user.avatar else None))
        return
    logging_channels[ctx.guild.id] = ctx.channel.id
    await ctx.send(embed=discord.Embed(
        description=f"✅ Newly found Gimkit PINs will be sent to {ctx.channel.mention}.",
        color=int("50B4E6", 16)
    ).set_author(name="Slime Bot", icon_url=bot.user.avatar.url if bot.user.avatar else None))

@bot.command(aliases=["gc"], help="Get the logging channel of the server.")
async def get_channel(ctx):
    if ctx.guild.id in logging_channels:
        channel = bot.get_channel(logging_channels[ctx.guild.id])
        await ctx.send(embed=discord.Embed(
            description=f"📡 Current logging channel: {channel.mention}",
            color=int("50B4E6", 16)
        ).set_author(name="Slime Bot", icon_url=bot.user.avatar.url if bot.user.avatar else None))
    else:
        await ctx.send(embed=discord.Embed(
            description="❌ No logging channel set.",
            color=int("FA3939", 16)
        ).set_author(name="Slime Bot", icon_url=bot.user.avatar.url if bot.user.avatar else None))

@tasks.loop(seconds=5)
async def check_logs():
    while not log_queue.empty():
        msg = log_queue.get_nowait()
        print(msg)  # also print queued messages
        for guild_id, channel_id in logging_channels.items():
            channel = bot.get_channel(channel_id)
            if channel:
                embed = discord.Embed(description=msg, color=int("50B4E6", 16))
                embed.set_author(name="Slime Bot", icon_url=bot.user.avatar.url if bot.user.avatar else None)
                await channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not check_logs.is_running():
        check_logs.start()

bot.run(TOKEN)
