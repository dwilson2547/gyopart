import os
import influxdb_client

class InfluxUtils:

    org = None
    bucket = None
    _write_api = None
    _initialized = False
    instance = None

    def __init__(self, instance, url: str=None, org: str=None, token: str=None, bucket: str=None):

        if not bucket:
            bkt = os.getenv('INFLUX_BUCKET')
            bucket = bkt if bkt else None
        if not org:
            o = os.getenv('INFLUX_ORG')
            org = o if o else None
        if not token:
            tkn = os.getenv('INFLUX_TOKEN')
            token = tkn if tkn else None
        if not url:
            u = os.getenv('INFLUX_URL')
            url = u if u else None

        client = influxdb_client.InfluxDBClient(
            url=url,
            token=token,
            org=org
        )
        self.bucket = bucket
        self.org = org
        self.instance = instance

        self._write_api = client.write_api(write_options=influxdb_client.client.write_api.SYNCHRONOUS)

        print('InfluxUtils Init Successful')

    def post_point(self, measure: str, tags: dict, fields: dict, bucket:str=None):
        try:
            p = influxdb_client.Point(measure)
            for key in list(tags.keys()):
                p.tag(key, tags[key])
            for field in list(fields.keys()):
                p.field(field, fields[field])
            
            bkt = bucket if bucket else self.bucket

            self._write_api.write(bucket=bkt, org=self.org, record=p)
        except Exception as ex:
            print(ex)
            print('failed to post message to influx')
            return

    def get_tags(self):
        return {
            'instance': self.instance
        }
    
    def get_influx_stats(self, yr, mk, mdl, trm, eng, status=True):
        return {
            'year': yr, 
            'make': mk,
            'model': mdl,
            'trim': trm,
            'engine': eng,
            'status': 'running' if status else 'dead'
        }
