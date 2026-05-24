import json
from apache_iggy import IggyClient
from apache_iggy import SendMessage as Message
from src.config import settings


class IggyService:
    def __init__(self):
        self._client: IggyClient | None = None

    async def connect(self):
        self._client = IggyClient.from_connection_string(settings.iggy_connection_string)
        await self._client.connect()
        try:
            await self._client.create_stream(name=settings.iggy_stream)
        except Exception:
            pass
        try:
            await self._client.create_topic(
                stream=settings.iggy_stream,
                name=settings.iggy_scrape_topic,
                partitions_count=1,
                replication_factor=1,
            )
        except Exception:
            pass

    async def disconnect(self):
        if self._client:
            await self._client.disconnect()

    async def publish_scrape_job(self, job_id: int, config_id: int, site_type: str, url: str, triggered_by: str = "admin"):
        if not self._client:
            raise RuntimeError("IggyService not connected")
        payload = json.dumps({
            "job_id": job_id,
            "scrape_site_config_id": config_id,
            "site_type": site_type,
            "url": url,
            "triggered_by": triggered_by,
        })
        await self._client.send_messages(
            stream=settings.iggy_stream,
            topic=settings.iggy_scrape_topic,
            partitioning=0,
            messages=[Message(payload)],
        )


iggy_service = IggyService()
