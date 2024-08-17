#!/bin/bash

source ./.envrc

# Get the External IP Address: 
# eg. 35.212.155.210
IP=$( gcloud compute instances describe instance-20240817-102216 --zone=us-west1-a --project=gen-lang-client-0826027133 --format="get(networkInterfaces[0].accessConfigs[0].natIP)" )
echo $IP

# SSH into the Instance:
# gcloud compute ssh --zone "us-west1-a" "instance-glc-ec2-small-or-20240817-213831" --project "gen-lang-client-0826027133"
# gcloud compute ssh --zone "us-west1-a" "instance-glc-ec2-small-or-20240817-213831" --project "gen-lang-client-0826027133" --troubleshoot --tunnel-through-iap
gcloud compute ssh $INSTANCE_NAME --zone $ZONE --project $PROJECT_ID

# Install Environment
# sudo apt-get install python3
# python3 --version
# sudo apt-get install python3-pip
# sudo apt-get install python3-sshtunnel