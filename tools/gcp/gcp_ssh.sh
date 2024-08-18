#!/bin/bash

# source .envrc

INSTANCE_NAME="instance-glc-ec2-small-or-20240817-213831"
PROJECT_ID="gen-lang-client-0826027133"
ZONE="us-west1-a"

# Get the External IP Address: 
# eg. 35.212.155.210
IP=$( gcloud compute instances describe ${INSTANCE_NAME} --zone=${ZONE} --project=${PROJECT_ID} --format="get(networkInterfaces[0].accessConfigs[0].natIP)" )
echo $IP

# Install Environment:
gcloud compute ssh $INSTANCE_NAME --zone $ZONE --project $PROJECT_ID << EOF
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
EOF

# SSH into the Instance:
# gcloud compute ssh --zone "us-west1-a" "instance-glc-ec2-small-or-20240817-213831" --project "gen-lang-client-0826027133"
# gcloud compute ssh --zone "us-west1-a" "instance-glc-ec2-small-or-20240817-213831" --project "gen-lang-client-0826027133" --troubleshoot --tunnel-through-iap
gcloud compute ssh $INSTANCE_NAME --zone $ZONE --project $PROJECT_ID
