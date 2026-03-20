#!/usr/bin/env python3
"""
TeamSync AI — Local PostgreSQL Setup
Run once before starting the server.

Prerequisites:
    brew install postgresql (Mac) or sudo apt install postgresql (Ubuntu)
    sudo service postgresql start

Usage:
    python setup_db.py
"""

import subprocess
import sys

def run(cmd: str, check=True):
    print(f"  → {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ✗ Error: {result.stderr.strip()}")
        return False
    if result.stdout.strip():
        print(f"  ✓ {result.stdout.strip()}")
    return True

def setup():
    print("\n🔧 TeamSync AI — PostgreSQL Setup\n")

    print("1. Creating database user 'teamsync'...")
    run("psql -U postgres -c \"CREATE USER teamsync WITH PASSWORD 'teamsync';\"", check=False)

    print("\n2. Creating database 'teamsync'...")
    run("psql -U postgres -c \"CREATE DATABASE teamsync OWNER teamsync;\"", check=False)

    print("\n3. Granting privileges...")
    run("psql -U postgres -c \"GRANT ALL PRIVILEGES ON DATABASE teamsync TO teamsync;\"", check=False)

    print("\n✅ Done! Database is ready.")
    print("\nNext steps:")
    print("  1. cp .env.example .env    (fill in your API keys)")
    print("  2. pip install -r requirements.txt")
    print("  3. python main.py")
    print("\nThe schema.sql will be applied automatically on first run.\n")

if __name__ == "__main__":
    setup()