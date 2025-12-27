#!/bin/bash
###############################################################################
# Heating Automation Service Installation Script
###############################################################################
# Installs the heating control systemd service on Raspberry Pi using a
# Python virtual environment for dependency isolation.
#
# Usage:
#   sudo ./install_automation_services.sh
#
# Requirements:
#   - Run as root (sudo)
#   - Python 3 installed
#   - Repository cloned to /home/pi/homehub/
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/home/pi/homehub"
VENV_DIR="${INSTALL_DIR}/automation/.venv"
SERVICE_SOURCE="${INSTALL_DIR}/automation/services/automation-heating.service"
SERVICE_DEST="/etc/systemd/system/automation-heating.service"
PYTHON_REQUIREMENTS="${INSTALL_DIR}/automation/requirements.txt"

###############################################################################
# Check if running as root
###############################################################################
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: Please run as root (use sudo)${NC}"
    exit 1
fi

###############################################################################
# Check if repository exists
###############################################################################
if [ ! -d "${INSTALL_DIR}" ]; then
    echo -e "${RED}ERROR: Repository not found at ${INSTALL_DIR}${NC}"
    echo "Please clone the repository first:"
    echo "  git clone <repository_url> ${INSTALL_DIR}"
    exit 1
fi

###############################################################################
# Check directory structure
###############################################################################
echo -e "${YELLOW}Checking directory structure...${NC}"

if [ ! -d "${INSTALL_DIR}/automation/src" ]; then
    echo -e "${RED}ERROR: Source directory not found: ${INSTALL_DIR}/automation/src${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Directory structure verified${NC}"

###############################################################################
# Create Python virtual environment
###############################################################################
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"

if [ -d "${VENV_DIR}" ]; then
    echo -e "${YELLOW}Virtual environment already exists at ${VENV_DIR}${NC}"
    echo -e "${YELLOW}Removing existing venv and creating fresh one...${NC}"
    rm -rf "${VENV_DIR}"
fi

# Create venv as pi user (not root) so permissions are correct
echo -e "${YELLOW}Creating virtual environment...${NC}"
sudo -u pi python3 -m venv "${VENV_DIR}"
echo -e "${GREEN}✓ Virtual environment created at ${VENV_DIR}${NC}"

# Upgrade pip in venv
echo -e "${YELLOW}Upgrading pip in virtual environment...${NC}"
sudo -u pi "${VENV_DIR}/bin/pip" install --upgrade pip
echo -e "${GREEN}✓ pip upgraded${NC}"

###############################################################################
# Install Python dependencies in venv
###############################################################################
echo -e "${YELLOW}Installing Python dependencies in virtual environment...${NC}"

if [ -f "${PYTHON_REQUIREMENTS}" ]; then
    # Install only the required packages for heating control
    sudo -u pi "${VENV_DIR}/bin/pip" install paho-mqtt==1.6.1 PyYAML==6.0.2 python-dotenv==1.0.0
    echo -e "${GREEN}✓ Python dependencies installed in venv${NC}"
else
    echo -e "${YELLOW}WARNING: requirements.txt not found, installing core dependencies only${NC}"
    sudo -u pi "${VENV_DIR}/bin/pip" install paho-mqtt PyYAML python-dotenv
fi

# Verify installation
echo -e "${YELLOW}Verifying installed packages...${NC}"
"${VENV_DIR}/bin/pip" list | grep -E "paho-mqtt|PyYAML|python-dotenv"
echo -e "${GREEN}✓ Dependencies verified${NC}"

###############################################################################
# Install systemd service
###############################################################################
echo -e "${YELLOW}Installing systemd service...${NC}"

if [ ! -f "${SERVICE_SOURCE}" ]; then
    echo -e "${RED}ERROR: Service file not found: ${SERVICE_SOURCE}${NC}"
    exit 1
fi

# Copy service file
cp "${SERVICE_SOURCE}" "${SERVICE_DEST}"
echo -e "${GREEN}✓ Service file copied to ${SERVICE_DEST}${NC}"

# Reload systemd
systemctl daemon-reload
echo -e "${GREEN}✓ Systemd reloaded${NC}"

# Enable service (start on boot)
systemctl enable automation-heating.service
echo -e "${GREEN}✓ Service enabled (will start on boot)${NC}"

# Start service
systemctl start automation-heating.service
echo -e "${GREEN}✓ Service started${NC}"

###############################################################################
# Verify service status
###############################################################################
echo ""
echo -e "${YELLOW}Service Status:${NC}"
systemctl status automation-heating.service --no-pager -l

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Virtual environment location:"
echo "  ${VENV_DIR}"
echo ""
echo "Service management commands:"
echo "  Status:  sudo systemctl status automation-heating.service"
echo "  Start:   sudo systemctl start automation-heating.service"
echo "  Stop:    sudo systemctl stop automation-heating.service"
echo "  Restart: sudo systemctl restart automation-heating.service"
echo "  Logs:    journalctl -u automation-heating.service -f"
echo ""
echo "Configuration files:"
echo "  Service: ${SERVICE_DEST}"
echo "  Config:  ${INSTALL_DIR}/automation/src/heating_config.yaml"
echo "  Script:  ${INSTALL_DIR}/automation/src/heating_control.py"
echo "  Venv:    ${VENV_DIR}"
echo ""
echo "To manually activate the virtual environment:"
echo "  source ${VENV_DIR}/bin/activate"
echo ""
echo "To install additional packages:"
echo "  ${VENV_DIR}/bin/pip install <package_name>"
echo ""
