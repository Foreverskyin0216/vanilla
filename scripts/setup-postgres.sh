#!/bin/bash

# PostgreSQL setup script for Vanilla chatbot
# Supports macOS (Homebrew) and Linux (apt/yum)

set -e

POSTGRES_USER="${POSTGRES_USER:-vanilla}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-vanilla}"
POSTGRES_DB="${POSTGRES_DB:-vanilla}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

# Detect OS
detect_os() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "macos"
  elif [[ -f /etc/debian_version ]]; then
    echo "debian"
  elif [[ -f /etc/redhat-release ]] || [[ -f /etc/centos-release ]] || [[ -f /etc/alinux-release ]]; then
    echo "rhel"
  else
    echo "unknown"
  fi
}

OS=$(detect_os)
echo "Detected OS: ${OS}"

# Install PostgreSQL
install_postgres() {
  case $OS in
    macos)
      if ! command -v brew &> /dev/null; then
        echo "Error: Homebrew is not installed. Please install it first."
        exit 1
      fi
      if ! brew list postgresql@17 &> /dev/null; then
        echo "Installing PostgreSQL 17 via Homebrew..."
        brew install postgresql@17
      else
        echo "PostgreSQL 17 is already installed."
      fi
      # Start PostgreSQL service
      brew services start postgresql@17
      # Add to PATH if needed (supports both Apple Silicon and Intel Macs)
      if [[ -d "/opt/homebrew/opt/postgresql@17/bin" ]]; then
        export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
      elif [[ -d "/usr/local/opt/postgresql@17/bin" ]]; then
        export PATH="/usr/local/opt/postgresql@17/bin:$PATH"
      fi
      ;;

    debian)
      echo "Installing PostgreSQL on Debian/Ubuntu..."
      sudo apt-get update
      sudo apt-get install -y postgresql postgresql-contrib
      sudo systemctl enable postgresql
      sudo systemctl start postgresql
      ;;

    rhel)
      echo "Installing PostgreSQL on RHEL/CentOS/AliLinux..."
      sudo yum install -y postgresql-server postgresql-contrib || sudo dnf install -y postgresql-server postgresql-contrib
      sudo postgresql-setup --initdb || sudo postgresql-setup initdb || true
      sudo systemctl enable postgresql
      sudo systemctl start postgresql
      ;;

    *)
      echo "Error: Unsupported OS. Please install PostgreSQL manually."
      exit 1
      ;;
  esac
}

# Setup database and user
setup_database() {
  echo "Setting up database..."

  case $OS in
    macos)
      # On macOS, the current user is the superuser
      if ! psql -lqt | cut -d \| -f 1 | grep -qw "${POSTGRES_DB}"; then
        createdb "${POSTGRES_DB}" 2>/dev/null || true
      fi
      psql -q -d "${POSTGRES_DB}" -c "
        DO \$\$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${POSTGRES_USER}') THEN
            CREATE ROLE ${POSTGRES_USER} WITH LOGIN PASSWORD '${POSTGRES_PASSWORD}';
          END IF;
        END
        \$\$;
        GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_DB} TO ${POSTGRES_USER};
        GRANT ALL ON SCHEMA public TO ${POSTGRES_USER};
      "
      ;;

    debian|rhel)
      # On Linux, use postgres user
      sudo -u postgres psql -c "
        DO \$\$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${POSTGRES_USER}') THEN
            CREATE ROLE ${POSTGRES_USER} WITH LOGIN PASSWORD '${POSTGRES_PASSWORD}';
          END IF;
        END
        \$\$;
      " || true

      sudo -u postgres createdb "${POSTGRES_DB}" --owner="${POSTGRES_USER}" 2>/dev/null || true
      sudo -u postgres psql -d "${POSTGRES_DB}" -c "GRANT ALL ON SCHEMA public TO ${POSTGRES_USER};" || true

      # Update pg_hba.conf for password authentication
      PG_HBA=$(sudo -u postgres psql -t -c "SHOW hba_file;" | xargs)
      if [[ -n "$PG_HBA" ]] && ! sudo grep -q "host.*${POSTGRES_DB}.*${POSTGRES_USER}" "$PG_HBA"; then
        echo "Updating pg_hba.conf for password authentication..."
        echo "host    ${POSTGRES_DB}    ${POSTGRES_USER}    127.0.0.1/32    scram-sha-256" | sudo tee -a "$PG_HBA"
        echo "host    ${POSTGRES_DB}    ${POSTGRES_USER}    ::1/128         scram-sha-256" | sudo tee -a "$PG_HBA"
        sudo systemctl reload postgresql
      fi
      ;;
  esac
}

# Main
echo "=== Vanilla PostgreSQL Setup ==="
echo ""

install_postgres
setup_database

echo ""
echo "PostgreSQL setup complete!"
echo ""
echo "Connection string:"
echo "  postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
echo ""
echo "Add this to your .env file:"
echo "  POSTGRES_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
