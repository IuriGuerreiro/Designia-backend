@echo off
REM Designia Backend Setup and Run Script for Windows
REM This script sets up and runs the Designia backend with Daphne on 192.168.3.2:8001

setlocal enabledelayedexpansion

REM Configuration
set HOST=192.168.3.2
set PORT=8001
set PROJECT_DIR=%~dp0
set VENV_DIR=%PROJECT_DIR%.venv

echo 🚀 Designia Backend Setup Script
echo ===============================
echo 📍 Target Host: %HOST%
echo 🔌 Target Port: %PORT%
echo 📁 Project Dir: %PROJECT_DIR%
echo.

REM Function to print status
:print_status
echo [INFO] %~1
goto :eof

:print_success
echo [SUCCESS] %~1
goto :eof

:print_warning
echo [WARNING] %~1
goto :eof

:print_error
echo [ERROR] %~1
goto :eof

REM Check if Python is installed
call :print_status "Checking Python installation..."
python --version >nul 2>&1
if errorlevel 1 (
    call :print_error "Python is not installed or not in PATH. Please install Python 3.9+ first."
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
call :print_success "Python %PYTHON_VERSION% found"

REM Setup virtual environment
call :print_status "Setting up virtual environment..."
if not exist "%VENV_DIR%" (
    call :print_status "Creating virtual environment..."
    python -m venv "%VENV_DIR%"
    call :print_success "Virtual environment created"
) else (
    call :print_success "Virtual environment already exists"
)

REM Activate virtual environment
call :print_status "Activating virtual environment..."
call "%VENV_DIR%\Scripts\activate.bat"
call :print_success "Virtual environment activated"

REM Install dependencies
call :print_status "Installing Python dependencies..."
if not exist "%PROJECT_DIR%requirements.txt" (
    call :print_error "requirements.txt not found!"
    pause
    exit /b 1
)

python -m pip install --upgrade pip
pip install -r requirements.txt
call :print_success "Dependencies installed"

REM Check database configuration
call :print_status "Checking database configuration..."
if not exist "%PROJECT_DIR%.env" (
    call :print_warning ".env file not found. Creating from example..."
    if exist "%PROJECT_DIR%.env.example" (
        copy "%PROJECT_DIR%.env.example" "%PROJECT_DIR%.env" >nul
        call :print_success ".env file created from example"
        call :print_warning "Please edit .env file with your database credentials"
    ) else (
        call :print_error "No .env.example file found. Please create .env file manually."
        pause
        exit /b 1
    )
) else (
    call :print_success ".env file found"
)

REM Run database migrations
call :print_status "Running database migrations..."
python manage.py makemigrations
python manage.py migrate
call :print_success "Database migrations completed"

REM Check Redis (optional)
call :print_status "Checking Redis connection..."
redis-cli ping >nul 2>&1
if errorlevel 1 (
    call :print_warning "Redis CLI not found or Redis server not running."
    call :print_warning "You can still run the server, but Celery tasks won't work."
    call :print_warning "Install Redis for Windows or use WSL for full functionality."
) else (
    call :print_success "Redis server is running"
)

REM Create superuser if needed
call :print_status "Checking for superuser..."
python manage.py shell -c "from django.contrib.auth.models import User; print('Superuser exists' if User.objects.filter(is_superuser=True).exists() else 'No superuser')" 2>nul | findstr "Superuser exists" >nul
if errorlevel 1 (
    call :print_warning "No superuser found. You can create one later with:"
    echo   python manage.py createsuperuser
) else (
    call :print_success "Superuser already exists"
)

REM Start Daphne server
call :print_status "Starting Daphne ASGI server..."
echo.
echo 🎉 Designia Backend is starting!
echo 📡 Server: http://%HOST%:%PORT%
echo 🌐 WebSocket: ws://%HOST%:%PORT%
echo 📊 Admin: http://%HOST%:%PORT%/admin
echo.
echo Press Ctrl+C to stop the server
echo.

REM Run Daphne
python run_daphne.py --host %HOST% --port %PORT%

pause
