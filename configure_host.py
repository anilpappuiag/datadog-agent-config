import yaml
import boto3
import subprocess
import os
import tarfile
import shutil
import datetime
import platform
import zipfile
import logging
from argparse import ArgumentParser

IS_WINDOWS = platform.system().lower() == "windows"
IS_LINUX = platform.system().lower() == "linux"

log_file = "datadog_configure.log" if IS_WINDOWS else "/tmp/datadog_configure.log"
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

parser = ArgumentParser()
parser.add_argument("--config", dest="ssm_param_name", help="SSM Parameter Name for Datadog agent config")
parser.add_argument("--secrets_backend", dest="secrets_backend", help="Secrets backend archive")
parser.add_argument("--action", dest="action", help="install, update, or uninstall")
args = parser.parse_args()

def fetch_yaml_from_ssm(parameter_name):
    try:
        ssm = boto3.client("ssm", region_name="eu-west-1")
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        raw_value = response["Parameter"]["Value"]
        return yaml.safe_load(raw_value)
    except Exception as e:
        logging.error(f"Failed to fetch SSM parameter: {str(e)}")
        raise

class secrets_backend_config:
    @staticmethod
    def install_secrets_backend():
        try:
            target_dir = r"C:\ProgramData\Datadog" if IS_WINDOWS else "/etc/datadog-agent"
            os.makedirs(target_dir, exist_ok=True)
            if IS_WINDOWS:
                with zipfile.ZipFile(args.secrets_backend, "r") as zip_ref:
                    zip_ref.extractall(target_dir)
            else:
                with tarfile.open(args.secrets_backend, "r:gz") as tar:
                    tar.extractall(path=target_dir)
            logging.info("Secrets backend extracted")
        except Exception as e:
            logging.error(f"Error installing secrets backend: {e}")

    @staticmethod
    def update_backend_executable():
        if IS_LINUX:
            try:
                import pwd, grp
                file_path = "/etc/datadog-agent/datadog-secret-backend"
                uid = pwd.getpwnam("dd-agent").pw_uid
                gid = grp.getgrnam("dd-agent").gr_gid
                os.chown(file_path, uid, gid)
                os.chmod(file_path, 0o500)
                logging.info("Permissions set on secret backend binary")
            except Exception as e:
                logging.error(f"Error setting ownership: {e}")

    @staticmethod
    def config_secrets_file(config):
        secrets_config = config.get("datadog_secret_config", {})
        target = r"C:\ProgramData\Datadog\datadog-secret-backend.yaml" if IS_WINDOWS else "/etc/datadog-agent/datadog-secret-backend.yaml"
        try:
            with open(target, "w") as f:
                yaml.dump(secrets_config, f, default_flow_style=False)
            logging.info("Secrets backend config written")
            if IS_LINUX:
                import pwd, grp
                uid = pwd.getpwnam("dd-agent").pw_uid
                gid = grp.getgrnam("dd-agent").gr_gid
                os.chown(target, uid, gid)
                os.chmod(target, 0o400)
                logging.info("Permissions set on secret backend config")
        except Exception as e:
            logging.error(f"Error writing secrets config: {e}")

class configure_agent:
    @staticmethod
    def process_exists(name):
        try:
            result = subprocess.run(["pgrep", "-f", name], stdout=subprocess.PIPE)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def service_exists_windows(name):
        try:
            result = subprocess.run(["powershell", "-Command", f"Get-Service -Name {name}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def check_can_connect(config):
        instances = config.get("instances", [])
        if not instances:
            return False
        host = instances[0].get("host")
        port = instances[0].get("port")
        try:
            import socket
            with socket.create_connection((host, port), timeout=2):
                return True
        except Exception:
            return False

    @staticmethod
    def should_apply_integration(name, config):
        if name == "mysql":
            return configure_agent.process_exists("mysqld") if IS_LINUX else configure_agent.service_exists_windows("MySQL")
        if name in ["postgres", "oracle", "sqlserver"]:
            return configure_agent.check_can_connect(config)
        if name == "ibm_mq":
            return configure_agent.process_exists("runmqlsr") or configure_agent.service_exists_windows("IBM MQSeries")
        return configure_agent.process_exists(name) if IS_LINUX else configure_agent.service_exists_windows(name)

    @staticmethod
    def write_main_agent_config(agent_dir, config):
        try:
            with open(f"{agent_dir}/datadog.yaml", "w") as f:
                yaml.dump(config.get("datadog_config", {}), f, default_flow_style=False)
            logging.info("Main agent config written")
            if IS_LINUX:
                import pwd, grp
                uid = pwd.getpwnam("dd-agent").pw_uid
                gid = grp.getgrnam("dd-agent").gr_gid
                os.chown(f"{agent_dir}/datadog.yaml", uid, gid)
                os.chmod(f"{agent_dir}/datadog.yaml", 0o640)
        except Exception as e:
            logging.error(f"Error writing main agent config: {e}")

    @staticmethod
    def configure_integrations(agent_dir, config):
        datadog_checks = config.get("datadog_checks", {})
        for integration, details in datadog_checks.items():
            if not configure_agent.should_apply_integration(integration, details):
                logging.info(f"Skipping integration {integration} — Not applicable on this host")
                continue
            try:
                conf_dir = f"{agent_dir}/conf.d/{integration}.d/"
                os.makedirs(conf_dir, exist_ok=True)
                conf_file_path = f"{conf_dir}/conf.yaml"
                if os.path.exists(conf_file_path):
                    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                    shutil.copy2(conf_file_path, f"{conf_file_path}.{timestamp}.bak")
                with open(conf_file_path, "w") as f:
                    yaml.dump(details, f, default_flow_style=False)
                logging.info(f"Configured integration: {integration}")
            except Exception as e:
                logging.error(f"Error configuring {integration}: {e}")

class agent_commands:
    @staticmethod
    def restart_agent():
        try:
            if IS_LINUX:
                subprocess.run(["systemctl", "restart", "datadog-agent"], check=True)
            elif IS_WINDOWS:
                subprocess.run([
                    os.path.join(os.environ["ProgramFiles"], "Datadog", "Datadog Agent", "embedded3", "agent.exe"),
                    "restart-service"
                ], check=True)
            logging.info("Agent restarted")
        except Exception as e:
            logging.error(f"Agent restart failed: {e}")

if __name__ == "__main__":
    agent_dir = r"C:\ProgramData\Datadog" if IS_WINDOWS else "/etc/datadog-agent"
    try:
        config = fetch_yaml_from_ssm(args.ssm_param_name)
        configure_agent.write_main_agent_config(agent_dir, config)
        configure_agent.configure_integrations(agent_dir, config)
        secrets_backend_config.install_secrets_backend()
        secrets_backend_config.config_secrets_file(config)
        secrets_backend_config.update_backend_executable()
        agent_commands.restart_agent()
    except Exception as e:
        logging.error(f"Unhandled error: {str(e)}")
