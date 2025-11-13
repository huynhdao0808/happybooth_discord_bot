import discord
from discord import app_commands
from discord.ext import commands
from googleapiclient.discovery import build
from google.oauth2 import service_account
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import requests

print(f"🐍 Discord.py: {discord.__version__}")

# =================== LOAD ENV ===================
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1427177908023197738

CALENDAR_ID = "c639975ea536b3e98ba755a41c6304599125de557f50df142206f1270897f793@group.calendar.google.com"
SERVICE_ACCOUNT_FILE = "bot-discord-happybooth-6f2f696ad2e5.json"

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

SHEET_ID = "1oX1o6yt_ao_zALJ_s9DaYV_j3I98tucra4fCAJqMvCY"
SHEET_RANGE = "Sheet1!A:B"

# =================== DISCORD SETUP ===================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =================== GOOGLE SETUP ===================
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/spreadsheets.readonly"]
)
calendar_service = build("calendar", "v3", credentials=creds)
sheet_service = build("sheets", "v4", credentials=creds)

# =================== GOOGLE SHEETS MAPPING ===================
def get_discord_notion_mapping():
    """Fetch Discord↔Notion email mapping from Google Sheets"""
    try:
        sheet = sheet_service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SHEET_ID, range=SHEET_RANGE).execute()
        values = result.get("values", [])
        
        mapping = {}
        for i, row in enumerate(values[1:], start=2):  # Skip header, start=2 for row numbers
            if len(row) >= 2:
                notion_email = row[0].strip()
                discord_mention = row[1].strip()
                mapping[discord_mention] = notion_email
            else:
                print(f"Row {i}: Incomplete data - {row}")  # Debug incomplete rows
        
        print(f"✅ Loaded {len(mapping)} user mappings from Google Sheets")
        return mapping
    except Exception as e:
        print(f"❌ Error loading mapping: {e}")
        import traceback
        traceback.print_exc()  # Show full error traceback
        return {}

discord_to_notion = get_discord_notion_mapping()

# =================== NOTION HELPER ===================
def load_notion_users():
    """Load all workspace users and return dict {email: id, name: id}"""
    users = {}
    try:
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
        }
        r = requests.get("https://api.notion.com/v1/users?page_size=100", headers=headers)
        if r.status_code == 200:
            for u in r.json().get("results", []):
                if "person" in u:
                    email = u["person"].get("email")
                    name = u.get("name")
                    uid = u["id"]
                    if email:
                        users[email.lower()] = uid
                    if name:
                        users[name.lower()] = uid
        print(f"✅ Loaded {len(users)} Notion users")
    except Exception as e:
        print(f"❌ Error loading Notion users: {e}")
    return users

notion_users = load_notion_users()

def get_notion_user_id_by_email_or_name(value):
    """Return Notion user ID if exists"""
    if not value:
        return None
    return notion_users.get(value.lower())

def create_notion_task(title, assignee_discord, note=None, due_date=None, description=None, project=None, task_type=None, priority=None):
    """Create a Notion task page in database"""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    notion_email = discord_to_notion.get(assignee_discord)
    notion_user_id = get_notion_user_id_by_email_or_name(notion_email)

    properties = {
        "Task name": {"title": [{"text": {"content": title}}]},
        "Assignee": {"people": [{"id": notion_user_id}] if notion_user_id else []},
    }

    if due_date:
        properties["Due date"] = {"date": {"start": due_date}}
    
    if note:
        properties["Description"] = {"rich_text": [{"text": {"content": note}}]}
    elif description:
        properties["Description"] = {"rich_text": [{"text": {"content": description}}]}
    
    # Add project field (assuming it's a rich text or select property)
    if project:
        properties["Project"] = {"rich_text": [{"text": {"content": project}}]}
    
    # Add type field (assuming it's a select property)
    if task_type:
        properties["Type"] = {"select": {"name": task_type}}
    
    # Add priority field (assuming it's a select property)
    if priority:
        properties["Priority"] = {"select": {"name": priority}}

    data = {"parent": {"database_id": NOTION_DATABASE_ID}, "properties": properties}
    res = requests.post(url, headers=headers, json=data)
    if res.status_code == 200:
        return res.json().get("url")
    print("❌ Notion error:", res.text)
    return None


# =================== GOOGLE CALENDAR EVENT ===================
async def create_calendar_event(channel, title, date, time, duration):
    """Helper function to create calendar event and thread"""
    try:
        start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        duration_minutes = int(float(duration) * 60)
        end = start + timedelta(minutes=duration_minutes)
        event = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Ho_Chi_Minh"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Ho_Chi_Minh"},
        }
        created_event = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        link = created_event.get("htmlLink")
        thread = await channel.create_thread(name=title, auto_archive_duration=60)
        await thread.send(f"📅 **{title}** on {date} {time}\n👉 [View Event]({link})")
        return link, thread
    except Exception as e:
        print(f"❌ Error creating event: {e}")
        raise


# =================== EVENT SLASH COMMANDS ===================

@bot.tree.command(name="event", description="Create a Google Calendar event + thread")
@app_commands.describe(
    title="Event title",
    date="Date (YYYY-MM-DD)",
    time="Time (HH:MM 24h)",
    duration="Duration in hours (e.g. 1.5)"
)
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def slash_event(interaction: discord.Interaction, title: str, date: str, time: str, duration: float):
    await interaction.response.defer()
    try:
        link, thread = await create_calendar_event(interaction.channel, title, date, time, str(duration))
        await interaction.followup.send(f"✅ Event created!\n[View Event]({link}) | Thread: {thread.mention}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")

# -------------------- TASK SLASH COMMAND --------------------
@bot.tree.command(name="task", description="Create a Notion task (reply or assign manually)")
@app_commands.describe(
    title="Task title",
    assign="@mention to assign task (optional if replying to message)",
    project="Project name (optional)",
    type="Task type: Technical, Sale-Marketing, etc (optional)",
    priority="Priority: Low, Medium, High, Urgent (optional)",
    description="Extra details (optional)",
    due_date="Due date in YYYY-MM-DD format (optional, defaults to today)"
)
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def slash_task(
    interaction: discord.Interaction, 
    title: str, 
    assign: str, 
    project: str = None, 
    type: str = None, 
    priority: str = None,
    description: str = None,
    due_date: str = None
):
    await interaction.response.defer(ephemeral=False)

    try:
        # Validate priority if provided
        valid_priorities = ["Low", "Medium", "High", "Urgent"]
        if priority and priority not in valid_priorities:
            await interaction.followup.send(f"❌ Invalid priority. Use one of: {', '.join(valid_priorities)}")
            return

        # Parse due date or default to today
        task_due_date = due_date
        if due_date:
            try:
                # Validate date format
                datetime.strptime(due_date, "%Y-%m-%d")
            except ValueError:
                await interaction.followup.send("❌ Invalid date format. Use YYYY-MM-DD (e.g., 2025-10-30)")
                return
        else:
            # Default to today if no due date provided
            task_due_date = datetime.now().strftime("%Y-%m-%d")

        # If reply — note = replied message content, assignee = replied message author
        note, assignee_discord = None, assign

        # Extract username from mention format <@123456789> or <@!123456789>
        discord_username = None
        if assignee_discord.startswith('<@') and assignee_discord.endswith('>'):
            user_id = assignee_discord.strip('<@!>')
            try:
                user = await bot.fetch_user(int(user_id))
                discord_username = user.name  # Get the username for Google Sheets lookup
            except:
                await interaction.followup.send("❌ Could not find the mentioned user.")
                return
        else:
            discord_username = assignee_discord

        if interaction.message and interaction.message.reference:
            ref = interaction.message.reference
            replied_message = await interaction.channel.fetch_message(ref.message_id)
            note = replied_message.content

        if not discord_username:
            await interaction.followup.send("❌ No assignee found. Use reply or provide `assign=@username` parameter.")
            return

        notion_url = create_notion_task(
            title=title,
            assignee_discord=discord_username,  # Pass username instead of mention
            note=note,
            description=description,
            due_date=task_due_date,
            project=project,
            task_type=type,
            priority=priority
        )

        if notion_url:
            # Build response message with all details
            response = f"✅ Task created for **{assignee_discord}**!\n🔗 [{title}]({notion_url})\n"
            if project:
                response += f"📁 Project: {project}\n"
            if type:
                response += f"🏷️ Type: {type}\n"
            if priority:
                # Add emoji for priority
                priority_emoji = {
                    "Low": "🟢",
                    "Medium": "🟡", 
                    "High": "🟠",
                    "Urgent": "🔴"
                }
                response += f"{priority_emoji.get(priority, '⚪')} Priority: {priority}\n"
            response += f"📅 Due: {task_due_date}"
            
            await interaction.followup.send(response)
        else:
            await interaction.followup.send("❌ Failed to create Notion task.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")


# =================== READY & SYNC ===================
@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")
    try:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"✅ Synced {len(synced)} commands to guild {GUILD_ID}")
    except Exception as e:
        print(f"❌ Sync error: {e}")
    print("🎉 Bot is ready!")

# =================== ERROR HANDLER ===================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(f"❌ {error}", ephemeral=True)

# =================== RUN ===================
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ Missing DISCORD_TOKEN in .env")
        exit(1)
    bot.run(DISCORD_TOKEN)
