import discord
import aiohttp
import asyncio
import json
import os
import logging
import re
import random
import io
import time  # ДОДАНО ДЛЯ ТАЙМЕРА
from pathlib import Path
from itertools import cycle
from datetime import datetime, timezone

# ---------- НАЛАШТУВАННЯ ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else 0
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")

ADMIN_IDS = [
    598767470140063744,
]

START_TIME = datetime.now(timezone.utc)

STATE_FILE = Path("sent.json")
STATUS_FILE = Path("statuses.json") 
CHECK_INTERVAL = 30 # Інтервал перевірки в секундах
BASE_URL = "https://newsky.app/api/airline-api"
AIRPORTS_DB_URL = "https://raw.githubusercontent.com/mwgg/Airports/master/airports.json"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Глобальна змінна для бази
AIRPORTS_DB = {}
# 🆕 Чорний список для заборони реакцій (в оперативній пам'яті)
BANNED_WOW_MESSAGES = set()
# 🔥 Глобальна змінна-запобіжник від дублікатів
MONITORING_STARTED = False
LAST_TRAFFIC_TIME = 0.0  # ЗМІННА ДЛЯ ТАЙМЕРА !traffic
# 🆕 Змінна для збереження останнього повідомлення
last_sent_message = None

# ---------- ДОПОМІЖНІ ФУНКЦІЇ ----------
def load_state():
    if not STATE_FILE.exists(): return {}
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except: return {}

def save_state(state):
    try:
        if len(state) > 100: state = dict(list(state.items())[-50:])
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except: pass

# --- 🎭 СТАНДАРТНІ СТАТУСИ ---
DEFAULT_STATUSES = [
    {"type": "play", "name": "🕹️Tracking with Newsky.app"},
    {"type": "play", "name": "🕹️Playing AirportSim"},
    {"type": "play", "name": "✈️Playing Microsoft Flight Simulator 2024"},
    {"type": "listen", "name": "🎧LiveATC @ KBP"},
    {"type": "watch", "name": "🔴Watching Youtube KAZUAR AVIA"}
]

def load_statuses():
    if not STATUS_FILE.exists():
        return list(DEFAULT_STATUSES)
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        if not data: return list(DEFAULT_STATUSES)
        return data
    except:
        return list(DEFAULT_STATUSES)

def save_statuses():
    try:
        STATUS_FILE.write_text(json.dumps(status_list, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Failed to save statuses: {e}")

status_list = load_statuses()
status_cycle = cycle(status_list)

def clean_text(text):
    if not text: return ""
    text = re.sub(r"\(.*?\)", "", text)
    removals = ["International", "Regional", "Airport", "Aerodrome", "Air Base", "Intl"]
    for word in removals:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        text = pattern.sub("", text)
    return text.strip().strip(",").strip()

# --- 🌍 ЗАВАНТАЖЕННЯ БАЗИ ---
async def update_airports_db():
    global AIRPORTS_DB
    print("🌍 Downloading airports database...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(AIRPORTS_DB_URL) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    AIRPORTS_DB = {}
                    for k, v in data.items():
                        AIRPORTS_DB[k.upper()] = {
                            "country": v.get("country", "XX"),
                            "city": v.get("city", ""),
                            "name": v.get("name", "")
                        }
                    print(f"✅ Airports DB loaded! ({len(AIRPORTS_DB)} airports)")
                else:
                    print(f"⚠️ Failed to load airports DB: Status {resp.status}")
        except Exception as e:
            print(f"⚠️ Error loading DB: {e}")

def get_flag(country_code):
    if not country_code or country_code == "XX": return "🏳️"
    try:
        return "".join([chr(ord(c) + 127397) for c in country_code.upper()])
    except:
        return "🏳️"

# --- 🧠 РОЗУМНЕ ФОРМУВАННЯ НАЗВИ ---
def format_airport_string(icao, api_name):
    icao = icao.upper()
    db_data = AIRPORTS_DB.get(icao)
    
    if db_data:
        city = db_data.get("city", "") or ""
        name = db_data.get("name", "") or ""
        country = db_data.get("country", "XX")
        
        # 🔥 ВИПРАВЛЕННЯ НАЗВ МІСТ 🔥
        if city.lower() == "kiev": city = "Kyiv"
        name = name.replace("Kiev", "Kyiv")
        
        if city.lower() == "dnipropetrovsk": city = "Dnipro"
        name = name.replace("Dnipropetrovsk", "Dnipro")      

        if city.lower() == "kirovograd": city = "Kropyvnytskyi"
        name = name.replace("Kirovograd", "Kropyvnytskyi")

        if city.lower() == "nikolayev": city = "Mykolaiv"
        name = name.replace("Nikolayev", "Mykolaiv")

        if city.lower() == "odessa": city = "Odesa"
        name = name.replace("Odessa", "Odesa")

        if city.lower() == "vinnitsa": city = "Vinnytsia"
        name = name.replace("Vinnitsa", "Vinnytsia")

        if city.lower() == "zaporizhia": city = "Zaporizhzhia"
        name = name.replace("Zaporizhia", "Zaporizhzhia")

        if city.lower() == "larnarca": city = "Larnaca"
        name = name.replace("Larnarca", "Larnaca")

        if city.lower() == "Sharm el-Sheikh": city = "Sharm El Sheikh"
        name = name.replace("Sharm el-Sheikh", "Sharm El Sheikh")
        
        clean_name = clean_text(name)
        display_text = ""
        
        if city and clean_name:
            if city.lower() in clean_name.lower():
                display_text = clean_name
            else:
                display_text = f"{city} {clean_name}"
        elif clean_name:
            display_text = clean_name
        elif city:
            display_text = city
        else:
            display_text = clean_text(api_name)

        return f"{get_flag(country)} **{icao}** ({display_text})"
    
    flag = "🏳️"
    if len(icao) >= 2:
        prefix = icao[:2]
        manual_map = {'UK': 'UA', 'KJ': 'US', 'K': 'US', 'EG': 'GB', 'LF': 'FR', 'ED': 'DE', 'LP': 'PT', 'LE': 'ES', 'LI': 'IT', 'U': 'RU'}
        code = manual_map.get(prefix, "XX")
        if code != "XX": flag = get_flag(code)

    return f"{flag} **{icao}** ({clean_text(api_name)})"

def get_timing(delay):
    try:
        d = float(delay)
        if d > 15: return f"🔴 **Delay** (+{int(d)} min)"
        if d < -15: return f"🟡 **Early** ({int(d)} min)"
        return "🟢 **On time**"
    except: return "⏱️ **N/A**"

def format_time(minutes):
    if not minutes: return "00:00"
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"

def get_rating_square(rating):
    try:
        r = float(rating)
        if r >= 8.0: return "🟩"
        if r >= 6.0: return "🟨" 
        if r >= 4.0: return "🟧"
        return "🟥"
    except: return "⬜"

# --- FPM + G-Force Search ---
def get_landing_data(f, details_type):
    if details_type == "test":
        fpm = -random.randint(50, 400)
        g = round(random.uniform(0.9, 1.8), 2)
        return f"📉 **{fpm} fpm**, **{g} G**"

    fpm, g_force, found = 0, 0.0, False
    if "result" in f and "violations" in f["result"]:
        for v in f["result"]["violations"]:
            td = v.get("entry", {}).get("payload", {}).get("touchDown", {})
            if td:
                fpm, g_force, found = int(td.get("rate", 0)), float(td.get("gForce", 0)), True
                if found: break

    if not found and "landing" in f and f["landing"]:
        td = f["landing"]
        fpm, g_force, found = int(td.get("rate", 0)), float(td.get("gForce", 0)), True

    if not found:
        val = f.get("lastState", {}).get("speed", {}).get("touchDownRate")
        if val: 
            fpm = int(val)
            found = True

    if found and fpm != 0:
        fpm_val = -abs(fpm)
        g_str = f", **{g_force} G**" if g_force > 0 else ""
        return f"📉 **{fpm_val} fpm**{g_str}"
    
    return "📉 **N/A**"

async def fetch_api(session, path, method="GET", body=None):
    try:
        async with session.request(method, f"{BASE_URL}{path}", headers=HEADERS, json=body, timeout=10) as r:
            return await r.json() if r.status == 200 else None
    except: return None

# ---------- MESSAGE GENERATOR ----------
async def send_flight_message(channel, status, f, details_type="ongoing"):
    fid = f.get("_id") or f.get("id") or "test_id"
    if status == "Completed" or status == "Cancelled":
        flight_url = f"https://newsky.app/flight/{fid}"
    else:
        flight_url = f"https://newsky.app/map/{fid}"

    # --- ✈️ ВИЗНАЧЕННЯ ТИПУ РЕЙСУ (СМАЙЛИК) ---
    if f.get("schedule"):
        type_emoji = "<:schedule:1468002863740616804>"
    else:
        type_emoji = "<:freee:1468002913837252833>"

    # --- 🌐 ВИЗНАЧЕННЯ МЕРЕЖІ (VATSIM/IVAO/OFFLINE) ---
    net_data = f.get("network")
    # Якщо network немає або ім'я null, то OFFLINE
    net = (net_data.get("name") if isinstance(net_data, dict) else str(net_data)) or "OFFLINE"

    cs = f.get("flightNumber") or f.get("callsign") or "N/A"
    airline = f.get("airline", {}).get("icao", "")
    full_cs = f"{airline} {cs}" if airline else cs
    
    dep_str = format_airport_string(f.get("dep", {}).get("icao", ""), f.get("dep", {}).get("name", ""))
    arr_str = format_airport_string(f.get("arr", {}).get("icao", ""), f.get("arr", {}).get("name", ""))
    
    ac = f.get("aircraft", {}).get("airframe", {}).get("name", "A/C")
    pilot = f.get("pilot", {}).get("fullname", "Pilot")
    
    raw_pax = 0
    if details_type == "result":
        raw_pax = f.get("result", {}).get("totals", {}).get("payload", {}).get("pax", 0)
    
    if raw_pax == 0 and f.get("type") != "cargo":
        raw_pax = f.get("payload", {}).get("pax", 0)
    
    flight_type = f.get("type", "pax")
    
    # --- 🔥 ВИПРАВЛЕННЯ ВАГИ ВАНТАЖУ (ТІЛЬКИ З JSON) 🔥 ---
    cargo_kg = int(f.get("payload", {}).get("weights", {}).get("cargo", 0))

    if flight_type == "cargo":
        payload_str = f"📦 **{cargo_kg}** kg"
    else:
        payload_str = f"👫 **{raw_pax}** Pax  |  📦 **{cargo_kg}** kg"

    embed = None
    arrow = " \u2003➡️\u2003 "

    if status == "Departed":
        delay = f.get("delay", 0)
        
        # --- 🚕 РОЗРАХУНОК TAXI TIME ---
        taxi_str = ""
        try:
            # Newsky дає час у форматі ISO 8601 (наприклад, 2026-02-07T20:29:33.360Z)
            # Беремо час відправлення від гейту і час зльоту
            t_gate_str = f.get("depTimeAct")
            t_air_str = f.get("takeoffTimeAct")
            
            if t_gate_str and t_air_str:
                t_gate = datetime.fromisoformat(t_gate_str.replace("Z", "+00:00"))
                t_air = datetime.fromisoformat(t_air_str.replace("Z", "+00:00"))
                diff = t_air - t_gate
                taxi_min = int(diff.total_seconds() // 60)
                taxi_str = f"🚕 **Taxi:** {taxi_min} min\n\n"
        except Exception as e:
            print(f"Taxi Calc Error: {e}")

        desc = (
            f"{dep_str}{arrow}{arr_str}\n\n"
            f"✈️ **{ac}**\n\n"
            f"{get_timing(delay)}\n" 
            f"{taxi_str}"            
            f"👨‍✈️ **{pilot}**\n\n"
            f"🌐 **{net.upper()}**\n\n"
            f"{payload_str}"
        )
        embed = discord.Embed(title=f"{type_emoji} 🛫 {full_cs} departed", url=flight_url, description=desc, color=0x3498db)

    elif status == "Completed":
        t = f.get("result", {}).get("totals", {})
        dist = t.get("distance", 0)
        ftime = t.get("time", 0)
        
        raw_balance = int(t.get("balance", 0))
        formatted_balance = f"{raw_balance:,}".replace(",", ".")
        rating = f.get("rating", 0.0)
        delay = f.get("delay", 0)
        
        check_g = 0.0
        check_fpm = 0
        if "result" in f and "violations" in f["result"]:
            for v in f["result"]["violations"]:
                entry = v.get("entry", {}).get("payload", {}).get("touchDown", {})
                if entry:
                    check_g = float(entry.get("gForce", 0))
                    check_fpm = int(entry.get("rate", 0))
                    break 
        if check_g == 0 and "landing" in f:
            check_g = float(f["landing"].get("gForce", 0))
            check_fpm = int(f["landing"].get("rate", 0) or f["landing"].get("touchDownRate", 0))

        title_text = f"{type_emoji} 😎 {full_cs} completed"
        color_code = 0x2ecc71
        rating_str = f"{get_rating_square(rating)} **{rating}**"

        # 🔥 Перевірка на краш (3G або 2000fpm) має пріоритет над Emergency 🔥
        is_hard_crash = abs(check_g) > 3.0 or abs(check_fpm) > 2000
        
        time_info_str = f"{get_timing(delay)}\n\n"

        if is_hard_crash: 
            title_text = f"{type_emoji} 💥 {full_cs} CRASHED"
            color_code = 0x992d22 
            rating_str = "💀 **CRASH**"
            formatted_balance = "-1.000.000" 
            time_info_str = "" 
        
        elif f.get("emergency") is True or (raw_balance == 0 and dist > 1):
            title_text = f"{type_emoji} ⚠️ {full_cs} EMERGENCY"
            color_code = 0xe67e22 
            rating_str = "🟥 **EMEG**"
            
        landing_info = get_landing_data(f, details_type)

        desc = (
            f"{dep_str}{arrow}{arr_str}\n\n"
            f"✈️ **{ac}**\n\n"
            f"{time_info_str}" 
            f"👨‍✈️ **{pilot}**\n\n"
            f"🌐 **{net.upper()}**\n\n"
            f"{landing_info}\n\n" 
            f"{payload_str}\n\n"
            f"📏 **{dist}** nm  |  ⏱️ **{format_time(ftime)}**\n\n"
            f"💰 **{formatted_balance} $**\n\n"
            f"{rating_str}"
        )
        embed = discord.Embed(title=title_text, url=flight_url, description=desc, color=color_code)

    elif status == "Cancelled":
        flight_duration = 0
        if f.get("durationAct"):
            flight_duration = f.get("durationAct")
        elif f.get("takeoffTimeAct") and f.get("lastState", {}).get("timestamp"):
            try:
                takeoff = datetime.fromisoformat(f.get("takeoffTimeAct").replace("Z", "+00:00"))
                last_ping = datetime.fromtimestamp(f["lastState"]["timestamp"] / 1000, tz=timezone.utc)
                flight_duration = int((last_ping - takeoff).total_seconds() // 60)
            except: pass

        desc = (
            f"{dep_str}{arrow}{arr_str}\n\n"
            f"✈️ **{ac}**\n\n"
            f"📍 **Status:** Flight Cancelled / Connection Lost\n"
            f"⏱️ **Flight time:** ~{flight_duration} min\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"🌐 **{net.upper()}**\n\n"
            f"{payload_str}"
        )
        embed = discord.Embed(title=f"⚫ {full_cs} flight cancelled", url=flight_url, description=desc, color=0x2b2d31)

    if embed:
        await channel.send(embed=embed)

async def change_status():
    current_status = next(status_cycle)
    activity_type = discord.ActivityType.playing
    if current_status["type"] == "watch":
        activity_type = discord.ActivityType.watching
    elif current_status["type"] == "listen":
        activity_type = discord.ActivityType.listening
    await client.change_presence(activity=discord.Activity(type=activity_type, name=current_status["name"]))

async def status_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await change_status()
        await asyncio.sleep(3600)

@client.event
async def on_message(message):
    global last_sent_message
    
    if message.author == client.user: return
    is_admin = False
    if message.author.id in ADMIN_IDS:
        is_admin = True
    elif message.guild and message.author.guild_permissions.administrator:
        is_admin = True
    
    # --- 📥 КОМАНДА: !cache (СКАЧАТИ ФАЙЛ ПАМ'ЯТІ) ---
    if message.content == "!cache":
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        
        if not STATE_FILE.exists() or os.path.getsize(STATE_FILE) == 0:
            return await message.channel.send("⚠️ **Cache file (sent.json) is empty or does not exist yet.**")
            
        await message.channel.send(
            content="📂 **Bot Memory File (sent.json):**", 
            file=discord.File(STATE_FILE)
        )
        return
    # --------------------------------------------------------

    # --- 🧹 КОМАНДА: !clearwow <ID> (ОЧИСТИТИ ВСІ РЕАКЦІЇ) ---
    if message.content.startswith("!clearwow"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split()
        if len(parts) < 2:
            return await message.channel.send("⚠️ Usage: `!clearwow <Message_ID>`")
        
        target_id = parts[1]
        
        if not target_id.isdigit():
             return await message.channel.send("⚠️ ID must be a number.")

        found_message = None
        
        main_channel = client.get_channel(CHANNEL_ID)
        if main_channel:
            try:
                found_message = await main_channel.fetch_message(int(target_id))
            except:
                pass
        
        if not found_message:
            await message.channel.send("🔍 **Searching for message...**")
            for guild in client.guilds:
                for channel in guild.text_channels:
                    if channel.id == CHANNEL_ID: continue
                    try:
                        found_message = await channel.fetch_message(int(target_id))
                        if found_message: break
                    except:
                        continue
                if found_message: break
        
        if found_message:
            try:
                await found_message.clear_reactions()
                
                # Якщо канал знайдено (не приватні повідомлення), робимо згадку
                channel_mention = found_message.channel.mention if hasattr(found_message.channel, 'mention') else "Direct Messages"
                await message.channel.send(f"✅ **Cleared all reactions from message in {channel_mention}**")
            except discord.Forbidden:
                await message.channel.send("❌ **Error:** I don't have 'Manage Messages' permission to clear reactions. Please check role settings.")
            except Exception as e:
                await message.channel.send(f"❌ **Error clearing reactions:** {e}")
        else:
            await message.channel.send("❌ **Message not found.** (Check ID or bot permissions)")
        return
    # -------------------------------------------------------------

    # --- 🛡️ КОМАНДА: !banwow <ID> (ЗАБОРОНИТИ СМАЙЛИ) ---
    if message.content.startswith("!banwow"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return await message.channel.send("⚠️ Usage: `!banwow <Message_ID>`")
        
        msg_id = int(parts[1])
        BANNED_WOW_MESSAGES.add(msg_id)
        await message.channel.send(f"🛡️ **Message {msg_id} is now protected!**\nБудь-які нові реакції будуть миттєво видалятися.")
        return

    # --- 🟢 КОМАНДА: !unbanwow <ID> (ДОЗВОЛИТИ СМАЙЛИ) ---
    if message.content.startswith("!unbanwow"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return await message.channel.send("⚠️ Usage: `!unbanwow <Message_ID>`")
        
        msg_id = int(parts[1])
        if msg_id in BANNED_WOW_MESSAGES:
            BANNED_WOW_MESSAGES.remove(msg_id)
            await message.channel.send(f"✅ **Protection removed.** Тепер на повідомлення {msg_id} знову можна ставити реакції.")
        else:
            await message.channel.send("⚠️ Це повідомлення і так не знаходиться у чорному списку.")
        return
    
    # --- 👹 КОМАНДА: !wow <ID> <EMOJI> (СТАВИТИ РЕАКЦІЮ) ---
    if message.content.startswith("!wow"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split()
        if len(parts) < 3:
            return await message.channel.send("⚠️ Usage: `!wow <Message_ID> <Emoji>`")
        
        target_id = parts[1]
        emoji = parts[2]
        
        if not target_id.isdigit():
             return await message.channel.send("⚠️ ID must be a number.")

        found_message = None
        
        main_channel = client.get_channel(CHANNEL_ID)
        if main_channel:
            try:
                found_message = await main_channel.fetch_message(int(target_id))
            except:
                pass
        
        if not found_message:
            await message.channel.send("🔍 **Searching for message...**")
            for guild in client.guilds:
                for channel in guild.text_channels:
                    if channel.id == CHANNEL_ID: continue
                    try:
                        found_message = await channel.fetch_message(int(target_id))
                        if found_message: break
                    except:
                        continue
                if found_message: break
        
        if found_message:
            try:
                await found_message.add_reaction(emoji)
                await message.channel.send(f"✅ **Reacted {emoji} to message in {found_message.channel.mention}**")
            except Exception as e:
                await message.channel.send(f"❌ **Error adding reaction:** {e}")
        else:
            await message.channel.send("❌ **Message not found.** (Check ID or bot permissions)")
        return
    # -------------------------------------------------------------

    # --- 🗑️ КОМАНДА: !unwow <ID> <EMOJI> (ПРИБРАТИ РЕАКЦІЮ) ---
    if message.content.startswith("!unwow"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split()
        if len(parts) < 3:
            return await message.channel.send("⚠️ Usage: `!unwow <Message_ID> <Emoji>`")
        
        target_id = parts[1]
        emoji = parts[2]
        
        if not target_id.isdigit():
             return await message.channel.send("⚠️ ID must be a number.")

        found_message = None
        
        main_channel = client.get_channel(CHANNEL_ID)
        if main_channel:
            try:
                found_message = await main_channel.fetch_message(int(target_id))
            except:
                pass
        
        if not found_message:
            await message.channel.send("🔍 **Searching for message...**")
            for guild in client.guilds:
                for channel in guild.text_channels:
                    if channel.id == CHANNEL_ID: continue
                    try:
                        found_message = await channel.fetch_message(int(target_id))
                        if found_message: break
                    except:
                        continue
                if found_message: break
        
        if found_message:
            try:
                await found_message.remove_reaction(emoji, client.user)
                await message.channel.send(f"✅ **Removed {emoji} from message in {found_message.channel.mention}**")
            except Exception as e:
                await message.channel.send(f"❌ **Error removing reaction:** {e}")
        else:
            await message.channel.send("❌ **Message not found.** (Check ID or bot permissions)")
        return
    # -------------------------------------------------------------

    # --- 💬 НОВА КОМАНДА: !reply <ID> <text> (ВІДПОВІСТИ НА ПОВІДОМЛЕННЯ) ---
    if message.content.startswith("!reply"):
        if not is_admin: 
            return await message.channel.send("🚫 **Access Denied**")
        
        parts = message.content.split()
        if len(parts) < 3:
            return await message.channel.send("⚠️ Usage: `!reply <Message_ID> <text>`")
        
        target_id = parts[1]
        
        if not target_id.isdigit():
             return await message.channel.send("⚠️ ID must be a number.")

        content = " ".join(parts[2:])
        found_message = None
        
        main_channel = client.get_channel(CHANNEL_ID)
        if main_channel:
            try:
                found_message = await main_channel.fetch_message(int(target_id))
            except:
                pass
        
        if not found_message:
            await message.channel.send("🔍 **Searching for message to reply to...**")
            for guild in client.guilds:
                for channel in guild.text_channels:
                    if channel.id == CHANNEL_ID: continue
                    try:
                        found_message = await channel.fetch_message(int(target_id))
                        if found_message: break
                    except:
                        continue
                if found_message: break
        
        if found_message:
            try:
                sent_msg = await found_message.reply(content)
                last_sent_message = sent_msg # 🔥 Зберігаємо для команди !undo
                await message.channel.send(f"✅ **Replied to message in {found_message.channel.mention}:**\n{content}")
            except Exception as e:
                await message.channel.send(f"❌ **Error replying:** {e}")
        else:
            await message.channel.send("❌ **Message not found.** (Check ID or bot permissions)")
        return
    # -------------------------------------------------------------

    # --- 🔄 КОМАНДА: !undo (ВИДАЛИТИ ОСТАННЄ) ---
    if message.content == "!undo":
        if not is_admin: 
            return await message.channel.send("🚫 **Access Denied**")
        
        if last_sent_message:
            try:
                await last_sent_message.delete()
                await message.channel.send("🗑️ **Last !msg or !reply deleted.**")
                last_sent_message = None
            except discord.NotFound:
                await message.channel.send("⚠️ **Message already deleted or not found.**")
                last_sent_message = None
            except discord.Forbidden:
                await message.channel.send("❌ **Error:** I don't have permission to delete it.")
        else:
            await message.channel.send("⚠️ **Nothing to undo.** (I only remember the last `!msg` or `!reply`)")
        return
    # ------------------------------------------------

    # --- 📢 КОМАНДА: !msg [ID] <text> (ЗІ ЗБЕРЕЖЕННЯМ) ---
    if message.content.startswith("!msg"):
        if not is_admin: 
            return await message.channel.send("🚫 **Access Denied**")
        
        parts = message.content.split()
        if len(parts) < 2:
            return await message.channel.send("⚠️ Usage: `!msg [Channel_ID] text` or `!msg text`")
        
        target_channel = client.get_channel(CHANNEL_ID)
        content_start_index = 1
        
        potential_id = parts[1]
        
        if potential_id.isdigit() and len(potential_id) > 15:
            try:
                found_channel = await client.fetch_channel(int(potential_id))
                if found_channel:
                    target_channel = found_channel
                    content_start_index = 2
            except discord.NotFound:
                return await message.channel.send(f"❌ **Error:** Channel with ID `{potential_id}` not found.")
            except discord.Forbidden:
                return await message.channel.send(f"❌ **Error:** I see channel `{potential_id}`, but I don't have permission to write there.")
            except Exception as e:
                pass

        content = " ".join(parts[content_start_index:])
        
        if not content:
            return await message.channel.send("⚠️ Empty message.")
        
        if target_channel:
            try:
                sent_msg = await target_channel.send(content)
                last_sent_message = sent_msg 
                
                await message.channel.send(f"✅ **Sent to {target_channel.mention}:**\n{content}")
            except Exception as e:
                await message.channel.send(f"❌ **Error:** {e}")
        else:
            await message.channel.send("❌ **Error:** Default channel not found (check CHANNEL_ID)")
        return
    # ------------------------------------------------------------

    # --- 📡 КОМАНДА: !traffic (ПОКАЗАТИ АКТИВНІ РЕЙСИ) ---
    if message.content == "!traffic":
        global LAST_TRAFFIC_TIME
        current_time = time.time()
        
        # Перевірка на 10-секундну затримку
        if current_time - LAST_TRAFFIC_TIME < 10:
            remaining = int(10 - (current_time - LAST_TRAFFIC_TIME))
            warning_msg = await message.channel.send(f"⏳ **Please wait {remaining} seconds** before requesting traffic again.")
            await asyncio.sleep(3)
            try:
                await warning_msg.delete()
            except:
                pass
            return
            
        LAST_TRAFFIC_TIME = current_time
        
        # Відправляємо тимчасове повідомлення
        msg = await message.channel.send("🔄 **Fetching live traffic data...**")
        
        async with aiohttp.ClientSession() as session:
            ongoing = await fetch_api(session, "/flights/ongoing")
            
            # Якщо рейсів немає
            if not ongoing or "results" not in ongoing or len(ongoing["results"]) == 0:
                embed = discord.Embed(title="📡 Live Traffic - Ukraine Classic", description="🛬 Наразі небо чисте, активних рейсів немає.", color=0xf1c40f)
                return await msg.edit(content=None, embed=embed)
            
            # Збираємо рядки для кожного рейсу
            desc_lines = []
            for f in ongoing["results"]:
                cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                airline = f.get("airline", {}).get("icao", "")
                full_cs = f"{airline} {cs}".strip() if airline else cs
                
                pilot_data = f.get("pilot", {})
                pilot = pilot_data.get("fullname", "Unknown Pilot") if isinstance(pilot_data, dict) else "Unknown Pilot"
                
                ac_data = f.get("aircraft", {})
                ac = "A/C"
                if isinstance(ac_data, dict):
                    ac = ac_data.get("airframe", {}).get("name") or ac_data.get("icao") or "A/C"
                
                dep = f.get("dep", {}).get("icao", "???") if isinstance(f.get("dep"), dict) else "???"
                arr = f.get("arr", {}).get("icao", "???") if isinstance(f.get("arr"), dict) else "???"
                
                # Формуємо красивий мінімалістичний рядок
                desc_lines.append(f"`{full_cs}` • {pilot} • `{ac}` • {dep} ➔ {arr}")
            
            # Створюємо фінальний Ембед
            embed = discord.Embed(title="📡 Live Traffic - Ukraine Classic", description="\n".join(desc_lines), color=0x3498db)
            
            # Додаємо час оновлення знизу
            current_utc_time = datetime.now(timezone.utc).strftime('%H:%M')
            embed.set_footer(text=f"🔄 Оновлено: {current_utc_time} UTC | Newsky API")
            
            # Замінюємо "Fetching..." на готову картку
            await msg.edit(content=None, embed=embed)
        return
    # -------------------------------------------------------------

    # --- 📚 КОМАНДА: !help (ДИНАМІЧНА ДЛЯ КОРИСТУВАЧІВ ТА АДМІНІВ) ---
    if message.content == "!help":
        embed = discord.Embed(title="📚 Bot Commands", color=0x3498db)
        
        # Це бачать УСІ користувачі
        desc = "**🔹 User Commands:**\n"
        desc += "**`!help`** — Show command list\n"
        desc += "**`!traffic`** — Show active flights\n"
        
        # Це додається ТІЛЬКИ якщо користувач — адмін
        if is_admin:
            desc += "**🔒 Admin / System (Restricted):**\n"
            desc += "**`!status`** — System status\n"
            desc += "**`!test [min]`** — Run test scenarios\n"
            desc += "**`!spy <ID>`** — Dump flight JSON\n"
            desc += "**`!msg [ID] <text>`** — Send text message\n"
            desc += "**`!reply <ID> <text>`** — Reply to a message\n"
            desc += "**`!undo`** — Delete last !msg or !reply\n"
            desc += "**`!wow <ID> <emoji>`** — React to message\n"
            desc += "**`!unwow <ID> <emoji>`** — Remove reaction\n"
            desc += "**`!cache`** — Download sent.json memory\n\n"
            desc += "**🎭 Status Management (Admin):**\n"
            desc += "**`!next`** — Force next status\n"
            desc += "**`!addstatus <type> <text>`** — Save & Add status\n"
            desc += "**`!delstatus [num]`** — Delete status\n"
            
        embed.description = desc
        await message.channel.send(embed=embed)
        return
    # ----------------------------------------------------------------
    
    if message.content == "!next":
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        await change_status()
        await message.channel.send("✅ **Status switched!**")
        return

    if message.content.startswith("!addstatus"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split(maxsplit=2)
        if len(parts) < 3: return await message.channel.send("⚠️ Usage: `!addstatus <watch/play> <text>`")
        sType = parts[1].lower()
        if sType not in ["watch", "play", "listen"]: return await message.channel.send("⚠️ Use: `watch`, `play`, `listen`")
        status_list.append({"type": sType, "name": parts[2]})
        save_statuses()
        global status_cycle
        status_cycle = cycle(status_list)
        await message.channel.send(f"✅ Saved & Added: **{parts[2]}**")
        return

    if message.content.startswith("!delstatus"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split()
        if len(parts) == 1:
            list_str = "\n".join([f"`{i+1}.` {s['type'].upper()}: {s['name']}" for i, s in enumerate(status_list)])
            embed = discord.Embed(title="🗑️ Delete Status", description=f"Type `!delstatus <number>` to delete.\n\n{list_str}", color=0xe74c3c)
            return await message.channel.send(embed=embed)
        try:
            idx = int(parts[1]) - 1
            if 0 <= idx < len(status_list):
                if len(status_list) <= 1: return await message.channel.send("⚠️ Cannot delete the last status!")
                removed = status_list.pop(idx)
                save_statuses()
                status_cycle = cycle(status_list) 
                await message.channel.send(f"🗑️ Deleted & Saved: **{removed['name']}**")
            else:
                await message.channel.send("⚠️ Invalid number.")
        except ValueError:
            await message.channel.send("⚠️ Please enter a number.")
        return

    if message.content == "!status":
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        msg = await message.channel.send("🔄 **Checking Systems...**")
        api_status = "❌ API Error"
        flights_count = 0 
        
        async with aiohttp.ClientSession() as session:
            test = await fetch_api(session, "/flights/ongoing")
            if test is not None: 
                api_status = "✅ Connected to Newsky"
                if "results" in test:
                    flights_count = len(test["results"])
        
        launch_str = START_TIME.strftime("%d-%m-%Y %H:%M:%S UTC")

        embed = discord.Embed(title="🤖 Bot System Status", color=0x2ecc71)
        embed.add_field(name="📡 Newsky API", value=api_status, inline=False)
        embed.add_field(name="✈️ Active Flights", value=f"**{flights_count}** tracking", inline=False)
        embed.add_field(name="🌍 Airports DB", value=f"✅ Loaded ({len(AIRPORTS_DB)} airports)", inline=False)
        embed.add_field(name="📶 Discord Ping", value=f"**{round(client.latency * 1000)}ms**", inline=False)
        embed.add_field(name="🚀 Launched at", value=f"`{launch_str}`", inline=False)
        await msg.edit(content=None, embed=embed)
        return

    if message.content.startswith("!spy"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        try:
            parts = message.content.split()
            if len(parts) < 2: return await message.channel.send("⚠️ Usage: `!spy <ID>`")
            fid = parts[1]
            await message.channel.send(f"🕵️ **Analyzing {fid}...**")
            async with aiohttp.ClientSession() as session:
                data = await fetch_api(session, f"/flight/{fid}")
                if not data: return await message.channel.send("❌ API Error")
                file_bin = io.BytesIO(json.dumps(data, indent=4).encode())
                await message.channel.send(content=f"📂 **Dump {fid}:**", file=discord.File(file_bin, filename=f"flight_{fid}.json"))
        except Exception as e: await message.channel.send(f"Error: {e}")
        return

    if message.content.startswith("!test"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split()
        if len(parts) == 2:
            try:
                custom_delay = int(parts[1])
                await message.channel.send(f"🛠️ **Custom Test (Delay: {custom_delay} min)...**")
                mock_custom = {"_id": "test_custom", "flightNumber": "TEST1", "airline": {"icao": "OSA"}, "dep": {"icao": "UKBB", "name": "Boryspil"}, "arr": {"icao": "LPMA", "name": "Madeira"}, "aircraft": {"airframe": {"name": "B738"}}, "pilot": {"fullname": "Capt. Test"}, "payload": {"pax": 140, "cargo": 35}, "network": "VATSIM", "rating": 9.9, "landing": {"rate": -120, "gForce": 1.05}, "delay": custom_delay, "result": {"totals": {"distance": 350, "time": 55, "balance": 12500, "payload": {"pax": 140, "cargo": 35}}}}
                await send_flight_message(message.channel, "Completed", mock_custom, "test")
                return
            except ValueError: pass

        await message.channel.send("🛠️ **Running Full Test Suite...**")
        mock_dep = {"_id": "test_dep", "flightNumber": "TEST1", "airline": {"icao": "OSA"}, "dep": {"icao": "UKBB", "name": "Boryspil"}, "arr": {"icao": "LPMA", "name": "Madeira"}, "aircraft": {"airframe": {"name": "B738"}}, "pilot": {"fullname": "Capt. Test"}, "payload": {"pax": 145, "cargo": 35}, "delay": 2}
        await send_flight_message(message.channel, "Departed", mock_dep, "test")
        mock_norm = {"_id": "test_norm", "flightNumber": "TEST1", "airline": {"icao": "OSA"}, "dep": {"icao": "UKBB", "name": "Boryspil"}, "arr": {"icao": "LPMA", "name": "Madeira"}, "aircraft": {"airframe": {"name": "B738"}}, "pilot": {"fullname": "Capt. Test"}, "payload": {"pax": 100, "cargo": 40}, "network": "VATSIM", "rating": 9.9, "landing": {"rate": -150, "gForce": 1.1}, "delay": -10, "result": {"totals": {"distance": 350, "time": 55, "balance": 12500, "payload": {"pax": 100, "cargo": 40}}}}
        await send_flight_message(message.channel, "Completed", mock_norm, "test")
        mock_emerg = mock_norm.copy(); mock_emerg["_id"] = "test_emerg"; mock_emerg["emergency"] = True; mock_emerg["delay"] = 45; mock_emerg["result"] = {"totals": {"distance": 350, "time": 55, "balance": 0, "payload": {"pax": 100, "cargo": 40}}}
        await send_flight_message(message.channel, "Completed", mock_emerg, "test")
        mock_crash = mock_norm.copy(); mock_crash["_id"] = "test_crash"; mock_crash["landing"] = {"rate": -2500, "gForce": 4.5}; mock_crash["rating"] = 0.0; mock_crash["delay"] = 0; mock_crash["result"] = {"totals": {"distance": 350, "time": 55, "balance": -1150000, "payload": {"pax": 100, "cargo": 40}}}
        await send_flight_message(message.channel, "Completed", mock_crash, "test")
        return

async def main_loop():
    await client.wait_until_ready()
    await update_airports_db()
    
    channel = client.get_channel(CHANNEL_ID)
    state = load_state()
    first_run = True

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                ongoing = await fetch_api(session, "/flights/ongoing")
                if ongoing and "results" in ongoing:
                    print(f"📡 Tracking {len(ongoing['results'])} flights...", end='\r')
                    for raw_f in ongoing["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        
                        state.setdefault(fid, {})
                        
                        # --- 1. ЛІНИВА ПЕРЕВІРКА ---
                        if state[fid].get("takeoff"):
                            continue
                            
                        # --- 2. ШТУЧНА ЧЕРГА (ТРОТТЛІНГ) ---
                        await asyncio.sleep(2.5)
                        
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]
                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue
                        
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            await send_flight_message(channel, "Departed", f, "ongoing")
                            state[fid]["takeoff"] = True

                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for raw_f in recent["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if first_run:
                            state.setdefault(fid, {})["completed"] = True
                            continue
                        if fid in state and state[fid].get("completed"): continue
                        
                        # --- ЛОГІКА ДЛЯ ЗАКРИТИХ ТА ВИДАЛЕНИХ РЕЙСІВ ---
                        if raw_f.get("close"):
                            print(f"⏳ Waiting for calculation: {fid}")
                            await asyncio.sleep(3)
                            
                            det = await fetch_api(session, f"/flight/{fid}")
                            if not det or "flight" not in det: continue
                            f = det["flight"]
                            
                            # 🔥 ФІЛЬТР ПОКИНУТИХ РЕЙСІВ (ABANDONED) 🔥
                            t = f.get("result", {}).get("totals", {})
                            if t.get("distance", 0) == 0 and t.get("time", 0) == 0:
                                print(f"🙈 Ignored abandoned flight: {fid}")
                                state.setdefault(fid, {})["completed"] = True
                                continue

                            cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                            if cs == "N/A": continue

                            await send_flight_message(channel, "Completed", f, "result")
                            state.setdefault(fid, {})["completed"] = True
                            print(f"✅ Report Sent: {cs}")
                        
                        elif raw_f.get("deleted"):
                            await asyncio.sleep(2.5)
                            
                            det = await fetch_api(session, f"/flight/{fid}")
                            if not det or "flight" not in det: continue
                            f = det["flight"]
                            cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                            if cs == "N/A": continue

                            await send_flight_message(channel, "Cancelled", f, "ongoing")
                            state.setdefault(fid, {})["completed"] = True
                            print(f"⚫ Cancel Report Sent: {cs}")

                if first_run:
                    print("🔕 First run sync complete. No spam.")
                    first_run = False

                save_state(state)
            except Exception as e: print(f"Loop Error: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

# --- ⚡ РАДАР РЕАКЦІЙ (МИТТЄВЕ ВИДАЛЕННЯ) ---
@client.event
async def on_raw_reaction_add(payload):
    # Ігноруємо реакції самого бота (щоб він міг ставити смайли)
    if payload.user_id == client.user.id:
        return

    # Перевіряємо, чи є ID повідомлення у нашому чорному списку
    if payload.message_id in BANNED_WOW_MESSAGES:
        try:
            channel = client.get_channel(payload.channel_id)
            if not channel: return
            
            message = await channel.fetch_message(payload.message_id)
            
            # 🔥 ВИПРАВЛЕНО: Беремо юзера правильно, без звернення до порожнього кешу
            user = payload.member
            if not user:
                user = await client.fetch_user(payload.user_id)
            
            # Миттєво стираємо реакцію хулігана
            await message.remove_reaction(payload.emoji, user)
        except discord.Forbidden:
            print("⚠️ Помилка: Бот не має права 'Manage Messages' (Керування повідомленнями) на сервері!")
        except Exception as e:
            print(f"Помилка при видаленні реакції: {e}")

# --- 🚀 ЗАПУСК ГОЛОВНОГО ЦИКЛУ ---
@client.event
async def on_ready():
    global MONITORING_STARTED
    if MONITORING_STARTED: return
    MONITORING_STARTED = True
    
    print(f"✅ Bot online: {client.user}")
    print("🚀 MONITORING STARTED")
    client.loop.create_task(status_loop())
    client.loop.create_task(main_loop())

client.run(DISCORD_TOKEN)
