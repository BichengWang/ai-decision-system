#!/bin/bash

# Variables Setup
# INSTANCE_NAME="instance-20240817-102216"
# PROJECT_ID="gen-lang-client-0826027133"
# ZONE="us-west1-a"
source ./.envrc

# Get the External IP Address: 
# eg. 35.212.155.210
IP=$( gcloud compute instances describe instance-20240817-102216 --zone=us-west1-a --project=gen-lang-client-0826027133 --format="get(networkInterfaces[0].accessConfigs[0].natIP)" )
echo $IP

# SSH into the Instance:
# eg. gcloud compute ssh instance-20240817-102216 --project=gen-lang-client-0826027133 --zone=us-west1-a --troubleshoot --tunnel-through-iap
gcloud compute ssh $INSTANCE_NAME --zone $ZONE --project $PROJECT_ID

# Install Environment
# sudo apt-get install python3
# python3 --version
# sudo apt-get install python3-pip
# sudo apt-get install python3-sshtunnel