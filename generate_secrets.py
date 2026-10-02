"""Utility to generate a fresh .env file with random secret values.

This script is intended for local development only. The generated ``.env``
file is added to ``.gitignore`` so it will never be committed.
"""
import secrets
import os

def main() -> None:
    env_path = ".env"
    # Only overwrite if the user explicitly wants to (prevent accidental data loss)
    if os.path.exists(env_path):
        resp = input(f"{env_path} already exists – overwrite? [y/N]: ").strip().lower()
        if resp != "y":
            print("Aborted – existing .env preserved.")
            return
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"CAPITAL_API_KEY={secrets.token_urlsafe(32)}\n")
        f.write(f"CAPITAL_USERNAME={secrets.token_urlsafe(8)}\n")
        f.write(f"CAPITAL_PASSWORD={secrets.token_urlsafe(12)}\n")
        f.write("ENVIRONMENT=live\n")
        f.write("ALLOW_LIVE_TRADING=false\n")
        # Optional Telegram bot values (empty by default)
        f.write("TELEGRAM_BOT_TOKEN=\n")
        f.write("TELEGRAM_CHAT_ID=\n")
    print(f"Generated fresh secret .env at {env_path}")

if __name__ == "__main__":
    main()
