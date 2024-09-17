import os
import logging
import asyncio
import random
import sqlite3
from telethon import TelegramClient, errors
from telethon.errors import SessionPasswordNeededError
from cryptography.fernet import Fernet
from datetime import datetime
import sys

# Suppress Telethon detailed logs
logging.getLogger('telethon').setLevel(logging.CRITICAL)

# Paths and configurations
DB_FILE = 'telegram_bot_accounts.db'
ENCRYPTION_KEY_FILE = 'encryption_key.key'

# Anti-ban configurations
MIN_DELAY = 2  # Minimum delay between sending messages to different groups (in seconds)
MAX_DELAY = 4  # Maximum delay between sending messages to different groups (in seconds)

# ANSI escape codes for coloring the console output
RESET_COLOR = "\033[0m"
GREEN_COLOR = "\033[92m"
RED_COLOR = "\033[91m"
YELLOW_COLOR = "\033[93m"
BLUE_COLOR = "\033[94m"
CYAN_COLOR = "\033[96m"
MAGENTA_COLOR = "\033[95m"
BOLD_COLOR = "\033[1m"
UNDERLINE_COLOR = "\033[4m"

# Decorative symbols
HORIZONTAL_LINE = f"{CYAN_COLOR}{'═' * 60}{RESET_COLOR}"
STAR_BORDER = f"{MAGENTA_COLOR}{'*' * 60}{RESET_COLOR}"
ARROW_RIGHT = f"{CYAN_COLOR}➜{RESET_COLOR}"
CHECK_MARK = f"{GREEN_COLOR}✔{RESET_COLOR}"

# ASCII Art Banner - "ENERGETYCZNY"
BANNER = f"""
{BOLD_COLOR}{MAGENTA_COLOR}███████╗███╗   ██╗███████╗██████╗ ███████╗ ██████╗████████╗██╗   ██╗
██╔════╝████╗  ██║██╔════╝██╔══██╗██╔════╝██╔════╝╚══██╔══╝╚██╗ ██╔╝
███████╗██╔██╗ ██║█████╗  ██████╔╝███████╗██║        ██║    ╚████╔╝ 
╚════██║██║╚██╗██║██╔══╝  ██╔══██╗╚════██║██║        ██║     ╚██╔╝  
███████║██║ ╚████║███████╗██║  ██║███████║╚██████╗   ██║      ██║   
╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝   ╚═╝      ╚═╝{RESET_COLOR}
"""

# Encryption setup
if not os.path.exists(ENCRYPTION_KEY_FILE):
    key = Fernet.generate_key()
    with open(ENCRYPTION_KEY_FILE, 'wb') as f:
        f.write(key)
else:
    with open(ENCRYPTION_KEY_FILE, 'rb') as f:
        key = f.read()

cipher_suite = Fernet(key)

# Setup basic logging (errors/warnings only)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)

# SQLite database setup
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        api_id TEXT,
                        api_hash TEXT,
                        phone_number TEXT
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages_sent (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone_number TEXT,
                        group_id TEXT,
                        message TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )''')
    conn.commit()
    conn.close()

# Encryption and Decryption functions
def encrypt(data):
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt(data):
    return cipher_suite.decrypt(data.encode()).decode()

# Database operations
def add_account_to_db(api_id, api_hash, phone_number):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO accounts (api_id, api_hash, phone_number) 
                      VALUES (?, ?, ?)''',
                   (encrypt(api_id), encrypt(api_hash), encrypt(phone_number)))
    conn.commit()
    conn.close()

def load_accounts_from_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM accounts')
    accounts = cursor.fetchall()
    conn.close()
    return accounts

def record_message_sent(phone_number, group_id, message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO messages_sent (phone_number, group_id, message)
                      VALUES (?, ?, ?)''', (phone_number, group_id, message))
    conn.commit()
    conn.close()

# Function to read message from file
def read_message_from_file(phone_number, message_type):
    file_path = f"{phone_number}_{message_type}.txt"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"{RED_COLOR}Plik wiadomości {file_path} nie został znaleziony.{RESET_COLOR}")
        return None

# Function to list all groups the account belongs to
async def list_groups(client, phone_number):
    try:
        groups = []
        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                groups.append(f"{dialog.name} (ID: {dialog.id})")
                print(f'{CHECK_MARK} Znaleziono grupę: {dialog.name} (ID: {dialog.id})')
        
        # Save groups to file
        if groups:
            with open(f"{phone_number}_groups.txt", 'w', encoding='utf-8') as f:
                f.write("\n".join(groups))
            print(f"{GREEN_COLOR}Grupy zapisane w pliku: {phone_number}_groups.txt{RESET_COLOR}")
        else:
            print(f"{YELLOW_COLOR}Nie znaleziono żadnych grup dla konta {phone_number}.{RESET_COLOR}")
    
    except Exception as e:
        print(f"{RED_COLOR}Błąd podczas pobierania grup dla konta {phone_number}: {e}{RESET_COLOR}")

# Function to handle sending messages with anti-ban mechanisms and real-time counter display
async def send_messages(client, phone_number, message, message_counter):
    if not message:
        print(f"{RED_COLOR}Wiadomość nie została załadowana.{RESET_COLOR}")
        return

    try:
        sent_count = 0
        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                try:
                    # Delay before sending to avoid detection
                    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

                    # Send the message and record time
                    await client.send_message(dialog.id, message, parse_mode='md')
                    record_message_sent(phone_number, dialog.id, message)
                    sent_count += 1
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    # Update and print the real-time counter and group details
                    message_counter += 1
                    sys.stdout.write(f'{GREEN_COLOR}{CHECK_MARK} {message_counter}. Wysłano do grupy: {dialog.name} (ID: {dialog.id}) o {current_time}{RESET_COLOR}\n')
                    sys.stdout.flush()

                except errors.FloodWaitError as e:
                    print(f"{YELLOW_COLOR}Flood wait error. Sleeping for {e.seconds} seconds.{RESET_COLOR}")
                    await asyncio.sleep(e.seconds)
                except errors.UserBannedInChannelError:
                    print(f"{RED_COLOR}Zbanowano konto na grupie: {dialog.name} (ID: {dialog.id}).{RESET_COLOR}")
                except Exception as e:
                    print(f"{RED_COLOR}Błąd przy wysyłaniu do {dialog.name}: {e}{RESET_COLOR}")
    
    except Exception as e:
        print(f"{RED_COLOR}Błąd: {e}{RESET_COLOR}")

# Main function to handle individual account
async def handle_account(api_id, api_hash, phone_number, message_type, action):
    client = TelegramClient(f'session_{phone_number}', api_id, api_hash)
    message_counter = 0  # Real-time message counter
    
    try:
        await client.start(phone=phone_number)

        # Check if the session needs password (2FA)
        if not await client.is_user_authorized():
            try:
                await client.sign_in(phone=phone_number)
                code = input(f'Wprowadź kod wysłany na {phone_number}: ')
                await client.sign_in(code=code)
            except SessionPasswordNeededError:
                password = input('Wprowadź swoje hasło 2FA: ')
                await client.sign_in(password=password)

        # If action is "list_groups", list all the groups the bot is a member of
        if action == 'list_groups':
            await list_groups(client, phone_number)
        else:
            # Load the message from the appropriate .txt file
            message = read_message_from_file(phone_number, message_type)

            # Send messages to all groups with anti-ban mechanisms
            await send_messages(client, phone_number, message, message_counter)
    
    except Exception as e:
        print(f"{RED_COLOR}Błąd przy koncie {phone_number}: {e}{RESET_COLOR}")
    
    finally:
        await client.disconnect()

# Add new account to the bot
def add_account():
    print(BANNER)  # Show banner at start
    api_id = input(f"{BOLD_COLOR}{ARROW_RIGHT} Wprowadź API ID: {RESET_COLOR}")
    api_hash = input(f"{BOLD_COLOR}{ARROW_RIGHT} Wprowadź API Hash: {RESET_COLOR}")
    phone_number = input(f"{BOLD_COLOR}{ARROW_RIGHT} Wprowadź numer telefonu (z +): {RESET_COLOR}")

    print(f'Pamiętaj, aby utworzyć pliki "{phone_number}_standard.txt", "{phone_number}_premium.txt", "{phone_number}_announcement.txt".')

    add_account_to_db(api_id, api_hash, phone_number)
    print(f'{GREEN_COLOR}Konto dla numeru {phone_number} zostało dodane.{RESET_COLOR}')

# Menu-driven message selection
def select_message():
    print(f"\n{HORIZONTAL_LINE}\n{BOLD_COLOR}Wybierz typ wiadomości do wysyłania:{RESET_COLOR}")
    print(f"1. {CYAN_COLOR}Standard{RESET_COLOR}")
    print(f"2. {CYAN_COLOR}Premium{RESET_COLOR}")
    print(f"3. {CYAN_COLOR}Ogłoszenie{RESET_COLOR}")

    message_choice = input(f"{BOLD_COLOR}{ARROW_RIGHT} Twój wybór: {RESET_COLOR}")

    if message_choice == '1':
        return 'standard'
    elif message_choice == '2':
        return 'premium'
    elif message_choice == '3':
        return 'announcement'
    else:
        print(f"{RED_COLOR}Niepoprawny wybór, spróbuj ponownie.{RESET_COLOR}")
        return None

# Select action (either send messages or list groups)
def select_action():
    print(f"\n{HORIZONTAL_LINE}\n{BOLD_COLOR}Co chcesz zrobić?{RESET_COLOR}")
    print(f"1. {CYAN_COLOR}Wyślij wiadomości{RESET_COLOR}")
    print(f"2. {CYAN_COLOR}Wyświetl grupy konta{RESET_COLOR}")

    action_choice = input(f"{BOLD_COLOR}{ARROW_RIGHT} Twój wybór: {RESET_COLOR}")

    if action_choice == '1':
        return 'send_messages'
    elif action_choice == '2':
        return 'list_groups'
    else:
        print(f"{RED_COLOR}Niepoprawny wybór, spróbuj ponownie.{RESET_COLOR}")
        return None

# Main loop to control the bot
def main_loop():
    init_db()
    
    while True:
        print(f"\n{STAR_BORDER}\n{BOLD_COLOR}Telegram Bot Menu:{RESET_COLOR}")
        print(f"1. {BLUE_COLOR}Dodaj nowe konto{RESET_COLOR}")
        print(f"2. {BLUE_COLOR}Uruchom bota dla wszystkich kont{RESET_COLOR}")
        print(f"3. {BLUE_COLOR}Wyjdź{RESET_COLOR}")

        choice = input(f"{BOLD_COLOR}{ARROW_RIGHT} Wybierz opcję: {RESET_COLOR}")

        if choice == '1':
            add_account()
        elif choice == '2':
            accounts = load_accounts_from_db()
            if accounts:
                message_type = select_message()
                action = select_action()

                if message_type and action:
                    loop = asyncio.get_event_loop()
                    tasks = [handle_account(decrypt(account[1]), decrypt(account[2]), decrypt(account[3]), message_type, action) for account in accounts]
                    loop.run_until_complete(asyncio.gather(*tasks))
            else:
                print(f"{YELLOW_COLOR}Brak kont. Dodaj najpierw konto.{RESET_COLOR}")
        elif choice == '3':
            print(f"{GREEN_COLOR}Wyjście...{RESET_COLOR}")
            break
        else:
            print(f"{RED_COLOR}Nieprawidłowy wybór, spróbuj ponownie.{RESET_COLOR}")

if __name__ == '__main__':
    main_loop()
