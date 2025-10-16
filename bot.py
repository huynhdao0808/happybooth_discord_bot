import discord
from discord import app_commands
from discord.ext import commands
from googleapiclient.discovery import build
from google.oauth2 import service_account
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

print(f"🐍 Discord.py: {discord.__version__}")

# 🔒 SECURITY: Use environment variables instead!
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")  # Set this in your environment
GUILD_ID = 1427177908023197738
CALENDAR_ID = "c639975ea536b3e98ba755a41c6304599125de557f50df142206f1270897f793@group.calendar.google.com"
SERVICE_ACCOUNT_FILE = "bot-discord-happybooth-6f2f696ad2e5.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Google Calendar setup
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/calendar"]
)
service = build("calendar", "v3", credentials=creds)

async def create_calendar_event(channel, title, date, time, duration):
    """Helper function to create calendar event and thread"""
    try:
        start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        # Convert hours to minutes for timedelta
        duration_minutes = int(float(duration) * 60)
        end = start + timedelta(minutes=duration_minutes)
        
        event = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Ho_Chi_Minh"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Ho_Chi_Minh"},
        }
        
        created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        link = created_event.get("htmlLink")
        
        # Create thread
        thread = await channel.create_thread(name=title, auto_archive_duration=60)
        await thread.send(f"📅 **{title}** on {date} {time}\n👉 [View Event]({link})")
        
        return link, thread
    except Exception as e:
        print(f"❌ Error creating event: {e}")
        raise

# Text command (renamed to avoid conflict)
@bot.command(name="createevent")
async def text_event(ctx, title: str, date: str, time: str, duration: str):
    """Text command: !createevent "Title" YYYY-MM-DD HH:MM duration_in_hours"""
    await ctx.send("⏳ Creating event...")
    try:
        link, thread = await create_calendar_event(ctx.channel, title, date, time, duration)
        await ctx.send(f"✅ Event created! [View Event]({link}) | Thread: {thread.mention}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

# Slash command
@bot.tree.command(name="event", description="Create a calendar event with thread")
@app_commands.describe(
    title="Event title",
    date="Date in YYYY-MM-DD format",
    time="Time in HH:MM format (24h)",
    duration="Duration in hours (e.g., 1.5 for 1 hour 30 minutes)"
)
@app_commands.guilds(discord.Object(id=GUILD_ID))  # Guild-specific command
async def slash_event(
    interaction: discord.Interaction,
    title: str,
    date: str,
    time: str,
    duration: int
):
    """Slash command to create calendar event"""
    await interaction.response.defer()
    
    try:
        link, thread = await create_calendar_event(interaction.channel, title, date, time, str(duration))
        await interaction.followup.send(
            f"✅ Event created!\n[View Event]({link}) | Thread: {thread.mention}"
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"📊 Guild ID: {GUILD_ID}")
    print(f"🔍 Commands registered: {len(bot.tree.get_commands())}")
    
    # Sync commands to specific guild
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)  # Copy global commands to guild
        synced = await bot.tree.sync(guild=guild)
        
        print(f"✅ Successfully synced {len(synced)} command(s) to guild {GUILD_ID}")
        for cmd in synced:
            print(f"   📋 /{cmd.name}: {cmd.description}")
    except Exception as e:
        print(f"❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
    
    print("🎉 Bot is ready! Try using /event in your server!")

# Error handler for slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandInvokeError):
        await interaction.response.send_message(f"❌ Error: {str(error.original)}", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Error: {str(error)}", ephemeral=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR: DISCORD_TOKEN environment variable not set!")
        print("Set it with: export DISCORD_TOKEN='your_token_here'")
        exit(1)
    
    bot.run(DISCORD_TOKEN)