from	pydantic_settings	import	BaseSettings, SettingsConfigDict
class	Settings(BaseSettings):
    model_config =	SettingsConfigDict(env_file=".env",	env_prefix="SENTI_")
    database_url: str = "postgresql+psycopg://senti:senti_dev_pw@localhost:5432/sentismetric"
    data_dir: str =	"data"
    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    whatsapp_token:	str	= ""
    whatsapp_phone_number_id: str =	""
    alert_recipients: str = ""
    nse_max_rps: float = 3.0												
    poll_interval_seconds: int = 180
settings = Settings()