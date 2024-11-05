#!/bin/bash

# Install Environment

sudo apt-get update

# zsh
sudo apt-get install zsh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git $ZSH_CUSTOM/themes/powerlevel10k

sudo apt-get install python3
python3 --version
sudo apt-get install python3-pip
sudo apt-get install python3-sshtunnel