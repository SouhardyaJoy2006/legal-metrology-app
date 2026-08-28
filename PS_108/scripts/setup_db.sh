#!/usr/bin/env bash
# scripts/setup_db.sh
# ====================
# One-time database setup. Run this as a user with sudo access.
# Usage: bash scripts/setup_db.sh
#
# What it does:
#   1. Creates the PostgreSQL user 'bis_rag_user'
#   2. Creates the database 'bis_rag'
#   3. Grants all privileges
#
# After this, run:
#   python -m bis_rag.db.manage ping     # verify connection
#   python -m bis_rag.db.manage migrate  # create tables

set -e

DB_USER="bis_rag_user"
DB_PASS="bis_rag_pass"
DB_NAME="bis_rag"

echo "Setting up PostgreSQL database for BIS RAG..."

# Create user (ignore error if already exists)
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || \
    echo "  User '$DB_USER' already exists — skipping."

# Create database (ignore error if already exists)
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || \
    echo "  Database '$DB_NAME' already exists — skipping."

# Grant privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"

echo ""
echo "Done. Your credentials:"
echo "  DB:   $DB_NAME"
echo "  User: $DB_USER"
echo "  Pass: $DB_PASS"
echo ""
echo "Make sure .env has:"
echo "  POSTGRES_USER=$DB_USER"
echo "  POSTGRES_PASSWORD=$DB_PASS"
echo "  POSTGRES_DB=$DB_NAME"
echo ""
echo "Next: python -m bis_rag.db.manage ping"
