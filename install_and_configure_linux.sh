#!/bin/bash
set -e

# args from SSM:
#  $1 = ConfigurationTask  (install/update/uninstall)
#  $2 = agentConfigParameterName
#  $3 = runtimeArtifactsS3Path  (s3://…)
configTask="$1"
agentConfigParameterName="$2"
runtimeArtifactsS3Path="$3"

echo "=== STEP 1: Download artifacts & fetch config ==="
mkdir -p /tmp/datadog && cd /tmp/datadog

# make sure aws CLI is in PATH
export PATH=$PATH:/usr/local/bin
if ! command -v aws &>/dev/null; then
  echo "ERROR: AWS CLI not found" >&2
  exit 1
fi

# this is the line you verified works
aws s3 cp "${runtimeArtifactsS3Path}/datadog-agent-7-latest.amd64.rpm" . \
  || { echo "ERROR: failed to download RPM" >&2; exit 1; }

aws s3 cp "${runtimeArtifactsS3Path}/datadog-secret-backend-linux-amd64.tar.gz" . \
  || { echo "ERROR: failed to download secrets backend" >&2; exit 1; }

aws s3 cp "${runtimeArtifactsS3Path}/configure_host.py" . \
  || { echo "ERROR: failed to download configure_host.py" >&2; exit 1; }

aws ssm get-parameter --name "${agentConfigParameterName}" \
    --with-decryption --query 'Parameter.Value' --output text > agent-config.yaml \
  || { echo "ERROR: failed to fetch SSM parameter ${agentConfigParameterName}" >&2; exit 1; }

echo "STEP 1 complete."

echo "=== STEP 2: Install & configure Datadog Agent (${configTask}) ==="
yum localinstall datadog-agent-7-latest.amd64.rpm -y --nogpgcheck \
  || { echo "ERROR: yum install failed" >&2; exit 1; }

# run Python config
if [ -x /opt/datadog-agent/embedded/bin/python3 ]; then
  /opt/datadog-agent/embedded/bin/python3 configure_host.py \
    --config agent-config.yaml \
    --agent_installer datadog-agent-7-latest.amd64.rpm \
    --secrets_backend datadog-secret-backend-linux-amd64.tar.gz \
    --action "${configTask}" \
    || { echo "ERROR: configure_host.py failed" >&2; exit 1; }
  echo "STEP 2 complete."
else
  echo "ERROR: embedded Python not found" >&2
  exit 1
fi

echo "✅ All steps succeeded."
