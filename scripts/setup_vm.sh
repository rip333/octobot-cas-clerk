#!/bin/bash
# setup_vm.sh
# Run this script on a fresh Ubuntu VM (Google Compute Engine or similar)
# as your regular user (NOT root, but you must have sudo privileges).

set -e

echo "Starting Octobot CAS Clerk VM Setup..."

# 1. Update system and install dependencies
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git curl

# 2. Set up application directory
APP_DIR="/opt/octobot-cas-clerk"
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR

# 3. Clone repository
if [ ! -d "$APP_DIR/.git" ]; then
    echo "Cloning repository..."
    # Cloning via HTTPS to avoid needing SSH keys on the VM for public repos
    # Note: If this is a private repo, you MUST use SSH and configure a deploy key.
    git clone https://github.com/rip333/octobot-cas-clerk.git $APP_DIR
else
    echo "Repository already exists at $APP_DIR. Pulling latest..."
    cd $APP_DIR && git pull origin main
fi

# 4. Set up Python Virtual Environment
echo "Setting up Python virtual environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Create basic .env file if it doesn't exist
if [ ! -f "$APP_DIR/.env" ]; then
    echo "Creating empty .env file from template..."
    cp .env_template .env
    echo "⚠️ Please populate $APP_DIR/.env with your keys before starting the service!"
fi

# 6. Set up Systemd Service
echo "Creating systemd service..."
SERVICE_FILE="octobot.service"
cat > $SERVICE_FILE << EOF
[Unit]
Description=Octobot CAS Clerk Discord Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/discord_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo mv $SERVICE_FILE /etc/systemd/system/octobot.service

# 7. Reload systemd and enable service
echo "Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable octobot.service

echo ""
echo "==========================================================="
echo "Setup complete! ✅"
echo "IMPORTANT NEXT STEPS:"
echo "1. Edit the .env file with your tokens:"
echo "   nano $APP_DIR/.env"
echo "2. Place your GCP Service Account JSON key:"
echo "   nano $APP_DIR/gen-lang-client.json"
echo "3. Start the bot service:"
echo "   sudo systemctl start octobot.service"
echo "4. Check bot logs:"
echo "   sudo journalctl -u octobot -f"
echo "==========================================================="
