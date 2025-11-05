#!/bin/bash
# Designia Backend Setup and Run Script
# This script sets up and runs the Designia backend with Daphne on 192.168.3.2:8001

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
HOST="192.168.3.2"
PORT="8001"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo -e "${BLUE}🚀 Designia Backend Setup Script${NC}"
echo -e "${BLUE}===============================${NC}"
echo -e "📍 Target Host: ${GREEN}$HOST${NC}"
echo -e "🔌 Target Port: ${GREEN}$PORT${NC}"
echo -e "📁 Project Dir: ${GREEN}$PROJECT_DIR${NC}"
echo ""

# Function to print status
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Python is installed
check_python() {
    print_status "Checking Python installation..."
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3.9+ first."
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION found"
}

# Setup virtual environment
setup_venv() {
    print_status "Setting up virtual environment..."

    if [ ! -d "$VENV_DIR" ]; then
        print_status "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        print_success "Virtual environment created"
    else
        print_success "Virtual environment already exists"
    fi

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    print_success "Virtual environment activated"
}

# Install dependencies
install_dependencies() {
    print_status "Installing Python dependencies..."

    if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
        print_error "requirements.txt not found!"
        exit 1
    fi

    pip install --upgrade pip
    pip install -r requirements.txt
    print_success "Dependencies installed"
}

# Check database configuration
check_database() {
    print_status "Checking database configuration..."

    # Check if .env file exists
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        print_warning ".env file not found. Creating from example..."
        if [ -f "$PROJECT_DIR/.env.example" ]; then
            cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
            print_success ".env file created from example"
            print_warning "Please edit .env file with your database credentials"
        else
            print_error "No .env.example file found. Please create .env file manually."
            exit 1
        fi
    else
        print_success ".env file found"
    fi
}

# Run database migrations
run_migrations() {
    print_status "Running database migrations..."
    python manage.py makemigrations
    python manage.py migrate
    print_success "Database migrations completed"
}

# Check Redis
check_redis() {
    print_status "Checking Redis connection..."

    if ! command -v redis-cli &> /dev/null; then
        print_warning "Redis CLI not found. Please install Redis server."
        print_warning "You can still run the server, but Celery tasks won't work."
    else
        if redis-cli ping > /dev/null 2>&1; then
            print_success "Redis server is running"
        else
            print_warning "Redis server is not running. Starting Redis..."
            redis-server --daemonize yes
            sleep 2
            if redis-cli ping > /dev/null 2>&1; then
                print_success "Redis server started"
            else
                print_warning "Could not start Redis server. Celery tasks may not work."
            fi
        fi
    fi
}

# Create superuser if needed
create_superuser() {
    print_status "Checking for superuser..."

    # Check if superuser exists
    if python manage.py shell -c "from django.contrib.auth.models import User; print('Superuser exists' if User.objects.filter(is_superuser=True).exists() else 'No superuser')" 2>/dev/null | grep -q "Superuser exists"; then
        print_success "Superuser already exists"
    else
        print_warning "No superuser found. You can create one later with:"
        echo "  python manage.py createsuperuser"
    fi
}

# Start Daphne server
start_daphne() {
    print_status "Starting Daphne ASGI server..."
    echo ""
    echo -e "${GREEN}🎉 Designia Backend is starting!${NC}"
    echo -e "${BLUE}📡 Server:${NC} http://$HOST:$PORT"
    echo -e "${BLUE}🌐 WebSocket:${NC} ws://$HOST:$PORT"
    echo -e "${BLUE}📊 Admin:${NC} http://$HOST:$PORT/admin"
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
    echo ""

    # Run Daphne directly (fallback to module if PATH lacks daphne)
    if command -v daphne >/dev/null 2>&1; then
        daphne -b "$HOST" -p "$PORT" designiaBackend.asgi:application
    else
        python -m daphne -b "$HOST" -p "$PORT" designiaBackend.asgi:application
    fi
}

# Main execution
main() {
    cd "$PROJECT_DIR"

    check_python
    setup_venv
    install_dependencies
    check_database
    run_migrations
    check_redis
    create_superuser
    start_daphne
}

# Run main function
main "$@"
