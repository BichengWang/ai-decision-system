# GCP login

```shell
export INSTANCE_NAME="instance-20240817-102216"
export PROJECT_ID="gen-lang-client-0826027133"
export zone="us-west1-a"
gcloud compute instances describe INSTANCE_NAME --zone=ZONE --project=PROJECT_ID --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
gcloud compute ssh --zone "us-west1-a" "instance-20240817-102216" --project "gen-lang-client-0826027133"
```

