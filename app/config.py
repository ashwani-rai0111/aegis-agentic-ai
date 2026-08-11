from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://aegis:aegis@localhost:5432/aegis"
    openai_api_key: str | None = None
    openai_model_name: str = "gpt-4o-mini"
    # auto | crewai | deterministic
    aegis_agent_mode: str = "auto"
    aegis_verbose: bool = True
    max_actions_per_incident: int = 1

    # mock | aws — simulate incidents always use mock state when bootstrapped
    aegis_tool_backend: str = "mock"

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"
    aegis_ec2_instance_id: str | None = None
    aegis_cw_alarm_name: str | None = None
    aegis_healthcheck_url: str | None = None
    aegis_ssm_document: str = "AWS-RunShellScript"
    aegis_ssm_timeout_seconds: int = 90
    # Optional CloudWatch namespace/dimension for host metrics (CWAgent)
    aegis_cw_namespace: str = "CWAgent"
    aegis_pm2_bin: str = "pm2"
    # Linux user that owns the real PM2 daemon (auto-detected if empty)
    aegis_pm2_user: str | None = None
    # Comma-separated PM2 process names allowed for restart_pm2_process
    aegis_pm2_allowlist: str = (
        "signyn,signyardsnext,node-server,websites,api,worker"
    )

    # Live MySQL checks via SSM (socket/root on the EC2 host by default)
    aegis_mysql_enabled: bool = True
    aegis_mysql_host: str = "127.0.0.1"
    aegis_mysql_port: int = 3306
    # Leave user/password empty to use local socket auth (sudo/root mysql)
    aegis_mysql_user: str | None = None
    aegis_mysql_password: str | None = None
    aegis_mysql_prod_database: str = "signyards"
    aegis_mysql_staging_database: str = "uatsignyards"
    aegis_mysql_service_name: str = "mysql"
    # Mark unhealthy / severe when connections exceed this % of max_connections
    aegis_mysql_conn_saturation_pct: float = 90.0
    aegis_mysql_threads_running_warn: int = 50
    # After human approval, allow systemctl restart of MySQL on the instance
    aegis_mysql_restart_enabled: bool = True

    def pm2_allowlist(self) -> set[str]:
        return {
            part.strip()
            for part in (self.aegis_pm2_allowlist or "").split(",")
            if part.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
